"""Stage 1 실행 스크립트 — Mock/Live 테스트 및 Stage 1 -> Stage 2 연동 결과 파일(analysis_output.json) 생성.

사용법:
    python scripts/run_stage1.py --dry-run                           # API 키 없이 Mock 결과로 JSON 파일 생성
    python scripts/run_stage1.py --image path/to/photo.jpg           # 실호출 (API 키 필요)
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# 프로젝트 루트 import 설정
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from ai_pipeline.schemas.analysis import AnalysisResult
from ai_pipeline.schemas.user_input import ClothingCategory, UserInput
from ai_pipeline.services.stage1_narrative import analyze


SAMPLE_USER_INPUT = UserInput(
    category=ClothingCategory(main="상의", sub="셔츠"),
    material="데님",
    condition=["해짐", "색 바램"],
    story="아버지가 20년 넘게 입으신 데님 셔츠예요. 주말마다 이 셔츠를 입고 저를 자전거에 태워주셨어요.",
)


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="Stage 1 실행 및 분석 결과 JSON 생성")
    parser.add_argument("--image", default=None, help="옷 사진 경로 (선택)")
    parser.add_argument("--output", default="storage/sample_stage1_output.json", help="저장할 JSON 경로")
    parser.add_argument("--dry-run", action="store_true", help="API 키 없이 샘플 데이터로 Mock 분석 결과 생성")
    args = parser.parse_args()

    out_path = PROJECT_ROOT / args.output
    out_path.parent.mkdir(parents=True, exist_ok=True)

    if args.dry_run:
        print("💡 --dry-run 모드로 실행: API 키 없이 샘플 분석 결과를 저장합니다.")
        sample_result = AnalysisResult.model_validate({
            "visual": {
                "color_palette": ["#4A6B8A", "#D9CBB3"],
                "pattern": "무지",
                "material_user": SAMPLE_USER_INPUT.material,
                "material_estimate": "데님",
                "material_final": "데님",
                "condition_cues": SAMPLE_USER_INPUT.condition,
                "vibe_keywords": ["빈티지", "차분함", "추억"],
            },
            "story": {
                "polished": "아버지가 20년 넘게 입으신 데님 셔츠예요. 주말마다 이 셔츠를 입고 저를 자전거에 태워주셨어요.",
                "interpretation": "화자에게 이 셔츠는 아버지와의 주말, 자전거 뒷자리의 기억이다. 해진 소매는 세월이 아니라 함께한 시간의 증거로 해석된다.",
                "emotion_keywords": ["그리움", "따뜻함"],
            },
            "edition_name_candidates": ["Sunday Ride", "아버지의 주말", "Denim Years"],
            "certificate_text": "20년의 주말을 함께한 데님 셔츠로 제작된 단 하나의 에디션",
        })
        analysis_dict = sample_result.model_dump()
    else:
        print("🚀 Claude Sonnet (Stage 1) 실호출 진행 중...")
        result = analyze(image_path=args.image, user_input=SAMPLE_USER_INPUT)
        analysis_dict = result.model_dump()

    out_path.write_text(json.dumps(analysis_dict, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"✅ Stage 1 분석 결과가 성공적으로 저장되었습니다: {out_path.relative_to(PROJECT_ROOT)}")
    print(f"👉 Stage 2 연동 테스트를 실행하려면 다음 명령어를 입력하세요:\n")
    print(f"    python scripts/run_stage2.py --analysis {out_path.relative_to(PROJECT_ROOT)}\n")


if __name__ == "__main__":
    main()
