"""user_input 스키마 초안 검증 — Stage 1 담당자가 확장할 것."""
import pytest
from pydantic import ValidationError

from ai_pipeline.schemas.user_input import UserInput


def _valid_payload() -> dict:
    return {
        "category": {"main": "상의", "sub": "후드티"},
        "material": "면",
        "condition": ["해짐", "색 바램"],
        "story": "아버지가 20년 넘게 입으신 셔츠예요.",
    }


def test_valid_input_passes():
    ui = UserInput.model_validate(_valid_payload())
    assert ui.category.main == "상의"
    assert not ui.material_unknown


def test_material_unknown_flag():
    payload = _valid_payload() | {"material": "모르겠어요"}
    assert UserInput.model_validate(payload).material_unknown


def test_condition_is_optional():
    payload = _valid_payload()
    del payload["condition"]
    assert UserInput.model_validate(payload).condition == []


def test_sub_must_match_main():
    payload = _valid_payload()
    payload["category"] = {"main": "하의", "sub": "후드티"}  # 하의에 후드티 — 위반
    with pytest.raises(ValidationError):
        UserInput.model_validate(payload)


def test_etc_category_allows_free_sub():
    payload = _valid_payload()
    payload["category"] = {"main": "기타", "sub": "앞치마"}
    assert UserInput.model_validate(payload).category.sub == "앞치마"


def test_story_length_limit():
    payload = _valid_payload() | {"story": "가" * 501}
    with pytest.raises(ValidationError):
        UserInput.model_validate(payload)


def test_invalid_material_rejected():
    payload = _valid_payload() | {"material": "실크"}  # 토글에 없는 값
    with pytest.raises(ValidationError):
        UserInput.model_validate(payload)
