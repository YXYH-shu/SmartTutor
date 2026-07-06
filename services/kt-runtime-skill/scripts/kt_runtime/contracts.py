from dataclasses import asdict, dataclass, field
from typing import Any, Optional

class KTContractError(ValueError):
    pass


def _require_dict(payload: Any, name: str) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise KTContractError(f"{name} must be a JSON object.")
    return payload


def _normalize_binary(value: Any, field_name: str) -> int:
    try:
        normalized = int(value)
    except (TypeError, ValueError) as exc:
        raise KTContractError(f"{field_name} must be 0 or 1.") from exc
    if normalized not in (0, 1):
        raise KTContractError(f"{field_name} must be 0 or 1.")
    return normalized


def _normalize_optional_int(value: Any) -> Optional[int]:
    if value is None:
        return None
    return int(value)


@dataclass
class Observation:
    skill_id: int
    correct: int
    item_id: Optional[int] = None
    timestamp: Optional[str] = None
    extras: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "Observation":
        payload = _require_dict(payload, "student_trace item")
        if "skill_id" not in payload:
            raise KTContractError("student_trace item missing skill_id.")
        if "correct" not in payload:
            raise KTContractError("student_trace item missing correct.")
        return cls(
            skill_id=int(payload["skill_id"]),
            correct=_normalize_binary(payload["correct"], "student_trace.correct"),
            item_id=_normalize_optional_int(payload.get("item_id")),
            timestamp=payload.get("timestamp"),
            extras=dict(payload.get("extras", {})),
        )


@dataclass
class Target:
    skill_id: int
    item_id: Optional[int] = None
    observed_correct: Optional[int] = None
    extras: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "Target":
        payload = _require_dict(payload, "target item")
        if "skill_id" not in payload:
            raise KTContractError("target item missing skill_id.")
        observed_correct = payload.get("observed_correct")
        return cls(
            skill_id=int(payload["skill_id"]),
            item_id=_normalize_optional_int(payload.get("item_id")),
            observed_correct=(
                _normalize_binary(observed_correct, "target.observed_correct")
                if observed_correct is not None
                else None
            ),
            extras=dict(payload.get("extras", {})),
        )


@dataclass
class KTPredictRequest:
    request_id: str
    task: str
    student_trace: list[Observation]
    targets: list[Target]
    device: str = "cuda:0"
    analysis_enabled: bool = True
    analysis_context: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "KTPredictRequest":
        payload = _require_dict(payload, "request")
        task = str(payload.get("task") or "predict_correctness").strip()
        if task not in {"predict_correctness", "score_observations"}:
            raise KTContractError(
                "task must be one of: predict_correctness, score_observations."
            )
        analysis_context = payload.get("analysis_context", {})
        analysis_context = analysis_context if isinstance(analysis_context, dict) else {}

        request = cls(
            request_id=str(payload.get("request_id", "missing-request-id")),
            task=task,
            student_trace=[
                Observation.from_dict(item) for item in payload.get("student_trace", [])
            ],
            targets=[Target.from_dict(item) for item in payload.get("targets", [])],
            device=str(payload.get("device") or "cuda:0"),
            analysis_enabled=bool(payload.get("analysis_enabled", True)),
            analysis_context=dict(analysis_context),
        )
        request.validate()
        return request

    def validate(self) -> None:
        if not self.targets:
            raise KTContractError("targets must not be empty.")
        if self.task == "predict_correctness" and not self.student_trace:
            raise KTContractError(
                "student_trace must not be empty for predict_correctness."
            )
        if self.task == "score_observations":
            for index, target in enumerate(self.targets):
                if target.observed_correct is None:
                    raise KTContractError(
                        f"targets[{index}].observed_correct is required for score_observations."
                    )


@dataclass
class Prediction:
    target: dict[str, Any]
    probability_correct: Optional[float]
    observed_correct: Optional[int] = None
    extras: dict[str, Any] = field(default_factory=dict)


@dataclass
class KTPredictResponse:
    request_id: str
    status: str
    task: str
    message: str
    predictions: list[Prediction] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)
    model_info: dict[str, Any] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    llm_analysis: Optional[dict[str, Any]] = None

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["predictions"] = [asdict(prediction) for prediction in self.predictions]
        return payload
