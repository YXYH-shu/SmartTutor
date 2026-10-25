from kt_runtime.kt_cli_runtime import predict_via_kt_cli
from kt_runtime.request_factory import build_request_from_student_id


def predict_from_dict(payload: dict):
    return predict_via_kt_cli(payload)


def predict_from_student_id(
    student_id: str,
    *,
    raw_targets: str | None = None,
    config_path: str | None = None,
    request_id: str | None = None,
    device: str | None = None,
    history_limit: int | None = None,
    initial_query: str | None = None,
    history_context: str | None = None,
):
    payload = build_request_from_student_id(
        student_id=student_id,
        raw_targets=raw_targets,
        config_path=config_path,
        request_id=request_id,
        device=device,
        history_limit=history_limit,
        initial_query=initial_query,
        history_context=history_context,
    )
    payload["student_id"] = str(student_id)
    if history_limit is not None:
        payload["history_limit"] = int(history_limit)
    return predict_from_dict(payload)
