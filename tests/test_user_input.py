"""user_input 스키마 검증 — 2026-08-18 개편 선택지 기준 (상의/하의/원피스/아우터 + 직접입력)."""
import pytest
from pydantic import ValidationError

from ai_pipeline.schemas.user_input import CUSTOM_SUB, SUB_CATEGORIES, UserInput


def _valid_payload() -> dict:
    return {
        "category": {"main": "상의", "sub": "셔츠"},
        "material": "데님",
        "condition": ["해짐", "색 바램"],
        "story": "아버지가 20년 넘게 입으신 셔츠예요.",
    }


def test_valid_input_passes():
    ui = UserInput.model_validate(_valid_payload())
    assert ui.category.main == "상의"
    assert ui.category.resolved_sub == "셔츠"
    assert not ui.material_unknown


def test_material_unknown_flag():
    payload = _valid_payload() | {"material": "선택안함"}
    assert UserInput.model_validate(payload).material_unknown


def test_condition_is_optional():
    payload = _valid_payload()
    del payload["condition"]
    assert UserInput.model_validate(payload).condition == []


def test_sub_must_match_main():
    payload = _valid_payload()
    payload["category"] = {"main": "하의", "sub": "셔츠"}  # 하의에 셔츠 — 위반
    with pytest.raises(ValidationError):
        UserInput.model_validate(payload)


def test_all_confirmed_subcategories_valid():
    """확정된 대분류×중분류 조합 전수 검증 (직접입력은 sub_custom과 함께)."""
    for main, subs in SUB_CATEGORIES.items():
        assert subs, f"'{main}'의 중분류가 비어 있음"
        for sub in subs:
            payload = _valid_payload()
            category = {"main": main, "sub": sub}
            if sub == CUSTOM_SUB:
                category["sub_custom"] = "청재킷"
            payload["category"] = category
            UserInput.model_validate(payload)  # 예외 없으면 통과


def test_custom_sub_requires_text():
    """'직접입력' 선택 시 sub_custom 필수."""
    payload = _valid_payload()
    payload["category"] = {"main": "상의", "sub": CUSTOM_SUB}
    with pytest.raises(ValidationError):
        UserInput.model_validate(payload)


def test_custom_sub_resolved():
    payload = _valid_payload()
    payload["category"] = {"main": "아우터", "sub": CUSTOM_SUB, "sub_custom": "야구잠바"}
    ui = UserInput.model_validate(payload)
    assert ui.category.resolved_sub == "야구잠바"


def test_sub_custom_only_with_custom_sub():
    """일반 서브 선택인데 sub_custom을 보내면 거부 (계약 오용 방지)."""
    payload = _valid_payload()
    payload["category"] = {"main": "상의", "sub": "셔츠", "sub_custom": "이상한값"}
    with pytest.raises(ValidationError):
        UserInput.model_validate(payload)


def test_removed_main_categories_rejected():
    """구 대분류(의류/가방/악세사리)는 거부 — 재창조 카테고리로 이동함 (회귀 방지)."""
    for old_main in ("의류", "가방", "악세사리", "기타"):
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
