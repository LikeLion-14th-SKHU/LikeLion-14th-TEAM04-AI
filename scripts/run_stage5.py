"""Stage 5 확인용 실행 스크립트 — 큐레이션 품질 튜닝하며 반복 실행하는 용도.

사용법 (프로젝트 루트에서):
    python scripts/run_stage5.py                                  # 내장 샘플 사연 + 샘플 design_spec으로 실행
    python scripts/run_stage5.py --analysis path/to/analysis.json  # 커스텀 analysis.json 사용

실행마다:
    - 큐레이션 추천 결과(2~3개)를 콘솔에 출력
    - 전체 결과를 storage/stage5_runs/<시각>.json 에 저장
    - trace_id를 출력 (storage/logs/<trace_id>.jsonl 에서 토큰 사용량 확인)

⚠️ 실호출이므로 과금 발생 (Claude Sonnet 5 실호출).
"""
from __future__ import annotations

import argparse
import json
import sys
import uuid
from datetime import datetime
from pathlib import Path

# UTF-8 콘솔 출력 설정
sys.stdout.reconfigure(encoding="utf-8")

# 프로젝트 루트 import 설정
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from ai_pipeline.schemas.analysis import AnalysisResult
from ai_pipeline.schemas.design_spec import DesignSpec
from ai_pipeline.services.stage5_curation import generate_curation

# conftest.py가 단일 원천 — 여기서 중복 정의하지 않음
sys.path.insert(0, str(PROJECT_ROOT / "tests"))
from conftest import SAMPLE_ANALYSIS_DICT  # noqa: E402

SAMPLE_DESIGN_SPEC_DICT = {
    "concept_name": "Sunday Ride Hobo",
    "category": "가방",
    "category_reason": None,
    "base_product": "dessau-cognac",
    "risk_profile": "balanced",
    "intervention_level": 3,
    "creation_method": "데님 패널 바디 조합 및 어깨끈 자수 재현",
    "applied_elements": [
        {
            "from_element": "소매의 해진 스티치 자국",
            "to_element": "호보백 스트랩 가죽 자수",
            "reason": "아버지가 20년간 매일 메던 어깨끈 자국을 스트랩 스티치로 남김",
        }
    ],
    "image_prompt": "Combine denim panel into leather hobo bag. plain light-gray studio background, front view, product only, no props.",
}


def main() -> None:
    parser = argparse.ArgumentParser(description="Stage 5 럭셔리 큐레이션 실호출")
    parser.add_argument("--analysis", help="analysis.json 파일 경로")
    parser.add_argument("--design-spec", help="design_spec.json 파일 경로")
    args = parser.parse_args()

    if args.analysis:
        analysis_data = json.loads(Path(args.analysis).read_text(encoding="utf-8"))
        analysis = AnalysisResult.model_validate(analysis_data)
    else:
        analysis = AnalysisResult.model_validate(SAMPLE_ANALYSIS_DICT)

    if args.design_spec:
        ds_data = json.loads(Path(args.design_spec).read_text(encoding="utf-8"))
        design_spec = DesignSpec.model_validate(ds_data)
    else:
        design_spec = DesignSpec.model_validate(SAMPLE_DESIGN_SPEC_DICT)

    trace_id = str(uuid.uuid4())
    print("=" * 70)
    print("🚀 Stage 5 (럭셔리 큐레이션) 실호출 시작")
    print(f"   - Trace ID: {trace_id}")
    print(f"   - 사연 요약: {analysis.story.polished[:40]}...")
    print(f"   - 선택된 재창조 베이스 제품: {design_spec.base_product}")
    print("=" * 70)

    try:
        curation = generate_curation(analysis, design_spec, trace_id=trace_id)
    except Exception as e:
        print(f"\n❌ [오류 발생]: {e}")
        sys.exit(1)

    print(f"\n✅ [큐레이션 완성] 추천 제품 {len(curation.recommendations)}개\n")

    for idx, rec in enumerate(curation.recommendations, 1):
        print(f"[{idx}] Product ID: {rec.product_id}")
        print(f"    - Tagline : \"{rec.tagline}\"")
        print(f"    - Reason  : {rec.reason}\n")

    # 결과 저장
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = PROJECT_ROOT / "storage" / "stage5_runs"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / f"{timestamp}.json"

    run_dump = {
        "trace_id": trace_id,
        "timestamp": timestamp,
        "base_product": design_spec.base_product,
        "curation_result": curation.model_dump(),
    }
    out_file.write_text(json.dumps(run_dump, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"📁 실행 결과 저장 완료: {out_file}")
    print(f"📊 사용량 트레이스 위치: storage/logs/{trace_id}.jsonl")


if __name__ == "__main__":
    main()
