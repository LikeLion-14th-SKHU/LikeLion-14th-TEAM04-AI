"""user_input 스키마 검증 — 2026-08-12 프론트 확정 선택지 기준."""
import pytest
from pydantic import ValidationError

from ai_pipeline.schemas.user_input import SUB_CATEGORIES, UserInput


def _valid_payload() -> dict:
    return {
        "category": {"main": "의류", "sub": "셔츠"},
        "material": "데님",
        "condition": ["해짐", "색 바램"],
        "story": "아버지가 20년 넘게 입으신 셔츠예요.",
    }


def test_valid_input_passes():
    ui = UserInput.model_validate(_valid_payload())
    assert ui.category.main == "의류"
    assert not ui.material_unknown


def test_material_unknown_flag():
    payload = _valid_payload() | {"material": "선택안함"}
    assert UserInput.model_validate(payload).material_unknown


def test_old_material_unknown_value_rejected():
    """구 명칭 '모르겠어요'는 이제 거부 — 프론트 확정으로 '선택안함'으로 변경됨 (회귀 방지)."""
    payload = _valid_payload() | {"material": "모르겠어요"}
    with pytest.raises(ValidationError):
        UserInput.model_validate(payload)


def test_condition_is_optional():
    payload = _valid_payload()
    del payload["condition"]
    assert UserInput.model_validate(payload).condition == []


def test_sub_must_match_main():
    payload = _valid_payload()
    payload["category"] = {"main": "가방", "sub": "셔츠"}  # 가방에 셔츠 — 위반
    with pytest.raises(ValidationError):
        UserInput.model_validate(payload)


def test_all_confirmed_subcategories_valid():
    """확정된 대분류×중분류 조합 전수 검증 (프론트 토글 그대로)."""
    for main, subs in SUB_CATEGORIES.items():
        assert subs, f"'{main}'의 중분류가 비어 있음"
        for sub in subs:
            payload = _valid_payload()
            payload["category"] = {"main": main, "sub": sub}
            UserInput.model_validate(payload)  # 예외 없으면 통과


def test_removed_main_categories_rejected():
    """구 대분류(상의/하의/아우터/기타)는 거부 (회귀 방지)."""
    for old_main in ("상의", "하의", "아우터", "원피스·스커트", "기타"):
        payload = _valid_payload()
        payload["category"] = {"main": old_main, "sub": "셔츠"}
        with pytest.raises(ValidationError):
            UserInput.model_validate(payload)


def test_story_length_limit():
    payload = _valid_payload() | {"story": "가" * 501}
    with pytest.raises(ValidationError):
        UserInput.model_validate(payload)


def test_invalid_material_rejected():
    payload = _valid_payload() | {"material": "실크"}  # 토글에 없는 값
    with pytest.raises(ValidationError):
        UserInput.model_validate(payload)
