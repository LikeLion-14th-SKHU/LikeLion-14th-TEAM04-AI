import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest
from ai_pipeline.config import settings
from ai_pipeline.schemas.analysis import AnalysisResult
from ai_pipeline.schemas.user_input import ClothingCategory, UserInput
from ai_pipeline.services.stage1_narrative import analyze, _build_image_block


@pytest.fixture
def sample_user_input() -> UserInput:
    return UserInput(
        category=ClothingCategory(main="의류", sub="셔츠"),
        material="데님",
        condition=["해짐", "색 바램"],
        story="아버지가 20년 넘게 입으신 데님 셔츠예요. 주말마다 이 셔츠를 입고 저를 자전거에 태워주셨어요.",
    )


def test_user_input_validation(sample_user_input: UserInput):
    assert sample_user_input.category.main == "의류"
    assert sample_user_input.category.sub == "셔츠"
    assert sample_user_input.material == "데님"
    assert sample_user_input.material_unknown is False


def test_user_input_material_unknown():
    ui = UserInput(
        category=ClothingCategory(main="의류", sub="자켓"),
        material="선택안함",
        condition=["얼룩"],
        story="길에서 주운 가죽 자켓인데 재질을 잘 모르겠어요.",
    )
    assert ui.material_unknown is True


def test_build_image_block_file_not_found():
    with pytest.raises(FileNotFoundError):
        _build_image_block("non_existent_image.jpg")


@patch("ai_pipeline.services.stage1_narrative.llm_client.structured_call")
def test_analyze_mock_call(mock_structured_call, sample_user_input: UserInput, sample_analysis: AnalysisResult):
    # LLM 호출 결과를 sample_analysis mock으로 지정
    mock_structured_call.return_value = sample_analysis.model_dump()

    # 이미지가 없어도 input text와 함께 잘 호출되는지 검증
    result = analyze(image_path=None, user_input=sample_user_input)

    assert isinstance(result, AnalysisResult)
    assert result.visual.material_final == "데님"
    assert len(result.edition_name_candidates) == 3
    assert mock_structured_call.called


def _has_valid_api_key() -> bool:
    key = settings.anthropic_api_key or os.getenv("ANTHROPIC_API_KEY", "")
    return bool(key and key.startswith("sk-ant-api") and not key.endswith("..."))


@pytest.mark.skipif(
    not _has_valid_api_key(),
    reason="유효한 ANTHROPIC_API_KEY 없음 (.env 또는 환경변수)",
)
def test_analyze_live_smoke(sample_user_input: UserInput, tmp_path: Path):
    # API 키가 있을 경우 실호출 테스트 (테스트용 이미지 생성 후 전달)
    dummy_img = tmp_path / "test_cloth.png"
    from PIL import Image

    img = Image.new("RGB", (200, 200), color="navy")
    img.save(dummy_img)

    result = analyze(image_path=dummy_img, user_input=sample_user_input)

    assert isinstance(result, AnalysisResult)
    assert len(result.visual.color_palette) >= 1
    assert result.visual.material_final != ""
    assert result.story.polished != ""
