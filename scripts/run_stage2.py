"""Stage 2 확인용 실행 스크립트 — 품질 튜닝하며 반복 실행하는 용도.

사용법 (프로젝트 루트에서):
    python scripts/run_stage2.py                          # 자동 제안 모드, 내장 샘플 사연
    python scripts/run_stage2.py --category "미니 레더백"  # 카테고리 지정 모드
    python scripts/run_stage2.py --analysis my_case.json  # 다른 analysis.json으로 실행

실행마다:
- 후보 3개를 콘솔에 정리해 출력
- 전체 결과를 storage/stage2_runs/<시각>.json 에 저장 (튜닝 전후 비교용)
- trace_id를 출력 (storage/logs/<trace_id>.jsonl 에서 토큰 사용량 확인)

⚠️ 실호출이므로 과금 발생 (레퍼런스 이미지 3장 포함, 호출당 소액).
"""
from __future__ import annotations

import argparse
import json
import sys
import uuid
from datetime import datetime
from pathlib import Path

# 프로젝트 루트를 import 경로에 추가 (어디서 실행해도 동작)
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from ai_pipeline.config import settings  # noqa: E402
from ai_pipeline.schemas.analysis import AnalysisResult  # noqa: E402
from ai_pipeline.schemas.design_spec import CandidateList  # noqa: E402
from ai_pipeline.services.stage2_design import generate_design_specs  # noqa: E402

# conftest.py의 샘플과 동일한 사연 — 아버지의 데님 셔츠
SAMPLE_ANALYSIS = {
    "visual": {
        "color_palette": ["#4A6B8A", "#D9CBB3"],
        "pattern": "무지",
        "material_user": "데님",
        "material_estimate": "데님",
        "material_final": "데님",
        "condition_cues": ["소매 해짐", "색 바램"],
        "vibe_keywords": ["빈티지", "차분함"],
    },
    "story": {
        "polished": "아버지가 20년 넘게 입으신 데님 셔츠예요. 주말마다 이 셔츠를 입고 저를 자전거에 태워주셨어요.",
        "interpretation": "화자에게 이 셔츠는 아버지와의 주말, 자전거 뒷자리의 기억이다. 해진 소매는 세월이 아니라 함께한 시간의 증거로 해석된다.",
        "emotion_keywords": ["그리움", "따뜻함"],
    },
    "edition_name_candidates": ["Sunday Ride", "아버지의 주말", "Denim Years"],
    "certificate_text": "20년의 주말을 함께한 데님 셔츠로 제작된 단 하나의 에디션",
}

LEVEL_LABELS = {
    0: "컬러/무드 이식", 1: "패턴/그래픽 이식", 2: "원단 부분 사용",
    3: "하이브리드", 4: "해체·재구성", 5: "파생 굿즈",
}


def print_candidates(result: CandidateList) -> None:
    for i, c in enumerate(result.candidates, 1):
        print(f"\n{'=' * 70}")
        print(f"후보 {i}: {c.concept_name}")
        print(f"{'=' * 70}")
        print(f"  프로파일   : {c.risk_profile}  (개입 강도 Lv{c.intervention_level} — {LEVEL_LABELS[c.intervention_level]})")
        print(f"  카테고리   : {c.category}")
        if c.category_reason:
            print(f"  선정 이유  : {c.category_reason}")
        print(f"  베이스 제품: {c.base_product}")
        print(f"  재창조 방식: {c.creation_method}")
        print("  요소 매핑:")
        for el in c.applied_elements:
            print(f"    - {el.from_element} → {el.to_element}")
            print(f"      이유: {el.reason}")
        print("  image_prompt:")
        print(f"    {c.image_prompt}")


def main() -> None:
    # Windows 콘솔(cp949)에서도 한글·특수문자가 깨지지 않게
    sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="Stage 2 실호출 확인")
    parser.add_argument("--category", default=None, help="목표 MCM 카테고리 (생략하면 자동 제안 모드)")
    parser.add_argument("--analysis", default=None, help="analysis.json 파일 경로 (생략하면 내장 샘플)")
    args = parser.parse_args()

    if args.analysis:
        raw = json.loads(Path(args.analysis).read_text(encoding="utf-8"))
    else:
        raw = SAMPLE_ANALYSIS
    analysis = AnalysisResult.model_validate(raw)

    mode = f"카테고리 지정 ({args.category})" if args.category else "자동 제안"
    trace_id = str(uuid.uuid4())
    print(f"모드: {mode} | 모델: {settings.llm_model} | trace_id: {trace_id}")
    print("호출 중... (십수 초 걸릴 수 있음)")

    result = generate_design_specs(analysis, target_category=args.category, trace_id=trace_id)
    print_candidates(result)

    # 튜닝 전후 비교를 위해 저장
    out_dir = PROJECT_ROOT / "storage" / "stage2_runs"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{datetime.now():%Y%m%d_%H%M%S}.json"
    out_path.write_text(
        json.dumps(
            {"mode": mode, "trace_id": trace_id, "result": result.model_dump()},
            ensure_ascii=False, indent=2,
        ),
        encoding="utf-8",
    )
    print(f"\n저장: {out_path.relative_to(PROJECT_ROOT)}")
    print(f"토큰 사용량: storage/logs/{trace_id}.jsonl (cache_read_input_tokens>0이면 캐싱 작동)")


if __name__ == "__main__":
    main()
