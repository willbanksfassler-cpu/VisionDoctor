"""Perform one explicitly enabled live DeepSeek Dataset Doctor verification."""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from generate_demo_dataset import generate_demo_zip

from vision_doctor.agent.client import diagnose_report_with_status
from vision_doctor.config import Settings
from vision_doctor.models import AuditReport
from vision_doctor.pipeline import run_pipeline


def main() -> int:
    """Run no more than one provider request and report only non-secret metadata."""

    settings = Settings()
    if not settings.live_api_test:
        print("实时 DeepSeek API 验证未启用；设置 VISION_DOCTOR_LIVE_API_TEST=1 后重试。")
        return 0

    if settings.llm.provider != "deepseek":
        print("实时验证未执行：VISION_DOCTOR_LLM__PROVIDER 必须为 deepseek。")
        return 0
    if not settings.llm.enabled:
        print("实时验证未执行：VISION_DOCTOR_LLM__ENABLED 必须为 true。")
        return 0
    if settings.llm.api_key is None or not settings.llm.model:
        print("实时验证未执行：缺少 DeepSeek API Key 或模型配置。")
        return 0

    one_attempt_llm = settings.llm.model_copy(update={"max_retries": 0})
    one_attempt_settings = settings.model_copy(update={"llm": one_attempt_llm})
    with tempfile.TemporaryDirectory(prefix="vision-doctor-deepseek-") as directory:
        temporary_root = Path(directory)
        archive = generate_demo_zip(temporary_root / "demo.zip")
        report = run_pipeline(
            archive,
            settings=one_attempt_settings,
            temp_root=temporary_root,
            run_doctor=False,
        )
        outcome = diagnose_report_with_status(report, one_attempt_llm)
        report = report.model_copy(update={"diagnosis": outcome.diagnosis})

    validated = AuditReport.model_validate_json(report.model_dump_json())
    diagnosis = validated.diagnosis
    generated_by = diagnosis.generated_by if diagnosis is not None else None
    failure_stage = (
        outcome.failure_stage.value if outcome.failure_stage is not None else None
    )
    print(
        json.dumps(
            {
                "provider": settings.llm.provider,
                "model": settings.llm.model,
                "generated_by": generated_by,
                "diagnosis_schema_valid": diagnosis is not None,
                "live_api_verified": outcome.live_api_verified,
                "failure_stage": failure_stage,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    if outcome.live_api_verified:
        print("真实 DeepSeek API 验证成功，Diagnosis 已通过 Pydantic 校验。")
        return 0
    print("真实 DeepSeek API 未验证成功，已使用 fallback。")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
