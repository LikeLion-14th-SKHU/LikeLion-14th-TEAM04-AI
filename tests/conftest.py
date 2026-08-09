import sys
from pathlib import Path

import pytest

# 프로젝트 루트를 import 경로에 추가 (pip install -e 없이 pytest 실행 가능하게)
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ai_pipeline.schemas.analysis import AnalysisResult  # noqa: E402


@pytest.fixture
def sample_analysis() -> AnalysisResult:
    """Stage 1 출력 예시 — 아버지의 낡은 데님 셔츠 사연."""
    return AnalysisResult.model_validate(
        {
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
    )
