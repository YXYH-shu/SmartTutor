from __future__ import annotations

import asyncio
import json
import os
import signal
from types import SimpleNamespace

import pytest

from app.services import lpp_integration


def prepare_worker(tmp_path, monkeypatch, source, *, timeout=2, cpu_threads=1):
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    (scripts / "run_lpp.py").write_text(source)
    monkeypatch.setattr(lpp_integration, "_skill_root", lambda: tmp_path)
    monkeypatch.setattr(
        lpp_integration.settings,
        "lpp",
        SimpleNamespace(timeout_seconds=timeout, cpu_threads=cpu_threads),
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("cpu_threads", [1, 2])
async def test_worker_uses_configured_threads_instead_of_inherited_host_defaults(
    tmp_path, monkeypatch, cpu_threads
):
    for key in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS"):
        monkeypatch.setenv(key, "64")
    payload = {
        "status": "ok",
        "message": "recommendations_ready",
        "recommendation": {
            "knowledge_points": [
                {"order": 1, "knowledge_point_id": 51, "knowledge_point_name": "电路元件"},
                {"order": 2, "knowledge_point_id": 80, "knowledge_point_name": "串并联"},
                {"order": 3, "knowledge_point_id": 81, "knowledge_point_name": "电阻"},
                {"order": 4, "knowledge_point_id": 82, "knowledge_point_name": "欧姆定律"},
                {"order": 5, "knowledge_point_id": 53, "knowledge_point_name": "安全用电"},
            ]
        },
    }
    prepare_worker(
        tmp_path,
        monkeypatch,
        "import json, os\n"
        f"result = json.loads({json.dumps(json.dumps(payload))})\n"
        "result['worker_threads'] = {k: os.environ.get(k) for k in "
        "['OMP_NUM_THREADS', 'MKL_NUM_THREADS', 'OPENBLAS_NUM_THREADS']}\n"
        "print(json.dumps(result))\n",
        cpu_threads=cpu_threads,
    )

    result = await lpp_integration._run_lpp_command([])

    assert result.data["worker_threads"] == {
        "OMP_NUM_THREADS": str(cpu_threads),
        "MKL_NUM_THREADS": str(cpu_threads),
        "OPENBLAS_NUM_THREADS": str(cpu_threads),
    }
    assert len(result.data["recommendation"]["knowledge_points"]) == 5


def is_alive(pid):
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


async def wait_for_pid(path):
    async with asyncio.timeout(2):
        while not path.exists():
            await asyncio.sleep(0.01)
    return int(path.read_text())


@pytest.mark.asyncio
@pytest.mark.parametrize("interrupt", ["cancel", "timeout"])
async def test_interrupted_planning_terminates_and_reaps_the_real_worker(
    tmp_path, monkeypatch, interrupt
):
    pid_file = tmp_path / "worker.pid"
    monkeypatch.setenv("LPP_TEST_PID_FILE", str(pid_file))
    prepare_worker(
        tmp_path,
        monkeypatch,
        "import os, time\nfrom pathlib import Path\n"
        "Path(os.environ['LPP_TEST_PID_FILE']).write_text(str(os.getpid()))\n"
        "while True: time.sleep(0.05)\n",
        timeout=0.2 if interrupt == "timeout" else 10,
    )
    task = asyncio.create_task(lpp_integration._run_lpp_command([]))
    pid = None
    try:
        pid = await wait_for_pid(pid_file)
        if interrupt == "cancel":
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
        else:
            with pytest.raises(RuntimeError, match="timed out"):
                await task
        assert not is_alive(pid), "The timed-out/cancelled planning worker was left running"
    finally:
        if pid is not None and is_alive(pid):
            os.killpg(pid, signal.SIGKILL)
            await asyncio.sleep(0.05)
        if not task.done():
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, RuntimeError):
                pass
