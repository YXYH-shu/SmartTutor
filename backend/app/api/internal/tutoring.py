"""POST /internal/v1/processTutoringInteraction — 课题五接入标准契约端点.

契约（依据《课题五接入外部能力标准规范》第二章/第五章）：
- 公共请求头 appId/userId/requestId/apiVersion 必填，userRole 可选。
- 请求体 {processingStage, data, ext?}；必须容忍未知扩展字段。
- 响应信封 {code, message, requestId, data}，000000 表示成功；
  带 degraded 标记的降级响应对应 000000（合法成功）。

请求头与请求体全部手工解析，保证任何校验错误都以标准信封返回，
不会泄漏 FastAPI 默认 422。
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app.api.internal.handlers import STAGE_HANDLERS, StageError

logger = logging.getLogger(__name__)

router = APIRouter(tags=["internal-v1"])

CODE_SUCCESS = "000000"
CODE_MISSING_FIELD = "200001"
CODE_BAD_VALUE = "200002"
CODE_INTERNAL = "900000"

REQUIRED_HEADERS = ("appId", "userId", "requestId", "apiVersion")


def _envelope(
    request_id: str,
    code: str,
    message: str,
    data: dict[str, Any] | None = None,
) -> JSONResponse:
    return JSONResponse(
        {
            "code": code,
            "message": message,
            "requestId": request_id,
            "data": data or {},
        }
    )


@router.post("/processTutoringInteraction")
async def process_tutoring_interaction(request: Request) -> JSONResponse:
    request_id = request.headers.get("requestId", "")

    # 1. 公共请求头校验 —— 缺失 200001，message 指出缺失字段
    missing = [h for h in REQUIRED_HEADERS if not request.headers.get(h)]
    if missing:
        return _envelope(
            request_id, CODE_MISSING_FIELD, f"公共请求头缺失: {', '.join(missing)}"
        )
    if request.headers["apiVersion"] != "v1":
        return _envelope(request_id, CODE_BAD_VALUE, "header apiVersion 仅支持 v1")

    # 2. 请求体解析 —— 手工解析，任何错误都落在标准信封里
    try:
        payload: Any = await request.json()
        if not isinstance(payload, dict):
            raise ValueError("请求体必须是 JSON 对象")
    except Exception:
        return _envelope(request_id, CODE_MISSING_FIELD, "请求体缺失或不是合法 JSON 对象")

    stage = payload.get("processingStage")
    if not stage:
        return _envelope(request_id, CODE_MISSING_FIELD, "processingStage 缺失")
    data = payload.get("data")
    if not isinstance(data, dict):
        return _envelope(request_id, CODE_MISSING_FIELD, "data 缺失或不是对象")

    handler = STAGE_HANDLERS.get(str(stage))
    if handler is None:
        supported = ", ".join(sorted(STAGE_HANDLERS))
        return _envelope(
            request_id,
            CODE_BAD_VALUE,
            f"processingStage 不支持: {stage}，当前支持: {supported}",
        )

    # 3. 分发 —— 参数错误按 StageError 返回码；处理器内部失败已自行转 degraded
    try:
        result = await handler(data, request.headers["userId"])
    except StageError as exc:
        return _envelope(request_id, exc.code, exc.message)
    except Exception:
        logger.exception(
            "processTutoringInteraction internal error, requestId=%s", request_id
        )
        return _envelope(
            request_id, CODE_INTERNAL, "服务内部异常，请凭 requestId 联系联调定位"
        )

    logger.info(
        "processTutoringInteraction stage=%s requestId=%s userId=%s degraded=%s",
        stage, request_id, request.headers["userId"], bool(result.get("degraded")),
    )
    return _envelope(request_id, CODE_SUCCESS, "success", result)
