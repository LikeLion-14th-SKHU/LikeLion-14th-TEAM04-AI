"""Stage 3 확인용 실행 스크립트 — Stage 2 결과로 컨셉 이미지를 실제 생성한다.

사용법 (프로젝트 루트에서):
    python scripts/run_stage3.py --clothing my_shirt.jpg
        → storage/stage2_runs/ 의 가장 최근 결과로 후보 3개 이미지 생성

    python scripts/run_stage3.py --clothing my_shirt.jpg --stage2-run storage/stage2_runs/20260809_1.json
    python scripts/run_stage3.py --clothing my_shirt.jpg --pro          # 발표용 (gemini-3-pro-image)
    python scripts/run_stage3.py --clothing my_shirt.jpg --candidate 0  # 특정 후보만

전제: 먼저 scripts/run_stage2.py 를 한 번 실행해 stage2_runs 결과가 있어야 한다.
⚠️ 실호출이므로 과금 발생 (이미지 생성 호출당).
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
from ai_pipeline.services.stage3_concept import generate_concept_images  # noqa: E402


def latest_stage2_run() -> Path:
    run_dir = PROJECT_ROOT / "storage" / "stage2_runs"
    runs = sorted(run_dir.glob("*.json")) if run_dir.exists() else []
    if not runs:
        sys.exit("storage/stage2_runs/ 에 결과가 없습니다 — 먼저 scripts/run_stage2.py 를 실행하세요")
    return runs[-1]


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="Stage 3 실호출 확인")
    parser.add_argument("--clothing", required=True, help="옷 사진 경로 (jpg/png)")
    parser.add_argument("--stage2-run", default=None, help="stage2_runs JSON 경로 (생략하면 최신)")
    parser.add_argument("--pro", action="store_true", help="발표용 모델(gemini-3-pro-image) 사용")
    parser.add_argument("--candidate", type=int, default=None, help="특정 후보 인덱스만 생성 (0부터)")
    args = parser.parse_args()

    clothing = Path(args.clothing)
    if not clothing.exists():
        sys.exit(f"옷 사진이 없습니다: {clothing}")

    run_path = Path(args.stage2_run) if args.stage2_run else latest_stage2_run()
    run_data = json.loads(run_path.read_text(encoding="utf-8"))
    candidates = CandidateList.model_validate(run_data["result"]).candidates

    if args.candidate is not None:
        candidates = [candidates[args.candidate]]

    model = settings.image_model_pro if args.pro else settings.image_model
    print(f"Stage 2 결과: {run_path.name} | 모델: {model} | 후보 {len(candidates)}개")
    print("생성 중... (장당 수 초~수십 초)")

    results = generate_concept_images(candidates, clothing, use_pro=args.pro)

    print(f"\n{'=' * 70}")
    for r in results:
        ref = r.reference_used or "(레퍼런스 없음 — base_product가 인덱스에 없어 프롬프트만으로 생성)"
        print(f"[{r.spec.risk_profile:^8}] {r.spec.concept_name}")
        print(f"           이미지: {r.image_path.relative_to(PROJECT_ROOT)}")
        print(f"           레퍼런스: {ref}")
    print(f"{'=' * 70}")
    print("이미지를 열어 확인하세요. 다음 단계: 게이트 채점 → 사용자 선택 → Meshy 3D")


if __name__ == "__main__":
    main()
