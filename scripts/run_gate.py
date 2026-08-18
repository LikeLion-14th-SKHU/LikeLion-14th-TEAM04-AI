"""검증 게이트 확인용 스크립트 — storage/images의 컨셉 이미지들을 Haiku로 채점.

사용법 (프로젝트 루트에서):
    python scripts/run_gate.py                    # 최신 stage2 결과 + storage/images 매칭 채점
    python scripts/run_gate.py --stage2-run storage/stage2_runs/xxx.json

이미지↔스펙 매칭: run_stage3.py가 저장한 파일명 접미사(_safe/_balanced/_bold)와
stage2 후보의 risk_profile을 대응시킨다.

⚠️ 실호출 (Haiku — 소액). 재생성은 이 스크립트에서 수행하지 않음 (전원 불합격 시 안내만).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from ai_pipeline.config import settings  # noqa: E402
from ai_pipeline.schemas.design_spec import CandidateList  # noqa: E402
from ai_pipeline.services.harness_gate import gate_with_retry  # noqa: E402
from ai_pipeline.services.stage3_concept import ConceptImage  # noqa: E402


def latest_stage2_run() -> Path:
    run_dir = PROJECT_ROOT / "storage" / "stage2_runs"
    runs = sorted(run_dir.glob("*.json")) if run_dir.exists() else []
    if not runs:
        sys.exit("storage/stage2_runs/ 가 비어 있음 — 먼저 scripts/run_stage2.py 실행")
    return runs[-1]


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="검증 게이트 실호출 확인")
    parser.add_argument("--stage2-run", default=None)
    args = parser.parse_args()

    run_path = Path(args.stage2_run) if args.stage2_run else latest_stage2_run()
    candidates = CandidateList.model_validate(
        json.loads(run_path.read_text(encoding="utf-8"))["result"]
    ).candidates

    # 파일명 접미사(_safe 등)로 이미지 ↔ 스펙 매칭
    concepts: list[ConceptImage] = []
    for spec in candidates:
        matches = sorted(settings.image_output_dir.glob(f"*_{spec.risk_profile}.jpg"))
        if not matches:
            print(f"⚠️ {spec.risk_profile} 컨셉 이미지 없음 — 건너뜀 (run_stage3.py 먼저)")
            continue
        concepts.append(
            ConceptImage(spec=spec, image_path=matches[-1], trace_id="", reference_used=None)
        )
    if not concepts:
        sys.exit("채점할 이미지가 없습니다")

    print(f"채점 대상 {len(concepts)}장 (모델: {settings.gate_model}) ...")
    outcome = gate_with_retry(concepts, regenerate=None)

    print(f"\n{'=' * 70}")
    for g in outcome.candidates:
        mark = "✅ 통과" if g.gate.passed else "❌ 불합격"
        print(f"{mark}  [{g.concept.spec.risk_profile:^8}] score={g.gate.score:3d}  {g.concept.image_path.name}")
        for r in g.gate.fail_reasons:
            print(f"          └ {r}")
    print(f"{'=' * 70}")
    if outcome.all_failed:
        print("⚠️ 전원 불합격 — 파이프라인에서는 fail_reasons 피드백으로 재생성 1회가 발동합니다")
    else:
        print(f"사용자에게 제시될 후보: {len(outcome.candidates)}장 (점수순)")


if __name__ == "__main__":
    main()
