"""재창조 목표 카테고리 (계층 구조, 2026-08-18 확정) — 목록·검증·API·레퍼런스-프리 테스트."""
from fastapi.testclient import TestClient

from ai_pipeline.main import app
from ai_pipeline.services import brand_assets

client = TestClient(app)


def test_taxonomy_structure():
    cats = brand_assets.available_categories()
    mains = [c["main"] for c in cats]
    assert mains == ["의류", "가방", "악세사리"]
    subs_by_main = {c["main"]: [s["sub"] for s in c["subs"]] for c in cats}
    assert "티셔츠" in subs_by_main["의류"] and "스커트" in subs_by_main["의류"]
    assert subs_by_main["가방"] == ["핸드백", "토트백", "백팩", "클러치", "트래블"]
    assert len(subs_by_main["악세사리"]) == 5


def test_reference_counts():
    cats = {c["main"]: c["subs"] for c in brand_assets.available_categories()}
    # 가방 21장이 서브 5종에 전부 배분됨 (빈 서브 없음)
    bag = {s["sub"]: s["count"] for s in cats["가방"]}
    assert sum(bag.values()) == 21 and all(n > 0 for n in bag.values())
    # 의류 서브도 전부 레퍼런스 보유
    assert all(s["count"] > 0 for s in cats["의류"])
    # 악세사리는 보유 0이지만 reference_free로 선택 가능
    assert all(s["count"] == 0 and s["reference_free"] for s in cats["악세사리"])
    assert all(not s["reference_free"] for s in cats["의류"] + cats["가방"])


def test_is_valid_category():
    assert brand_assets.is_valid_category("핸드백")
    assert brand_assets.is_valid_category("키링")
    assert not brand_assets.is_valid_category("가방")      # 메인은 target으로 불가 (서브만)
    assert not brand_assets.is_valid_category("신발")      # 재창조 대상에서 제외됨
    assert not brand_assets.is_valid_category("우산")


def test_is_reference_free():
    assert brand_assets.is_reference_free("지갑")
    assert not brand_assets.is_reference_free("핸드백")
    assert not brand_assets.is_reference_free("티셔츠")


def test_categories_endpoint_hierarchy():
    r = client.get("/ai/v1/recreation-categories")
    assert r.status_code == 200
    body = r.json()["categories"]
    assert [m["main"] for m in body] == ["의류", "가방", "악세사리"]
    acc = next(m for m in body if m["main"] == "악세사리")
    assert all(s["reference_free"] for s in acc["subs"])


def test_design_spec_rejects_unknown_category(sample_analysis):
    r = client.post(
        "/ai/v1/design-spec",
        json={"analysis": sample_analysis.model_dump(), "target_category": "우산"},
    )
    assert r.status_code == 422
    assert "우산" in r.json()["detail"]


def test_design_spec_rejects_main_as_target(sample_analysis):
    """메인('가방')이 아니라 서브('핸드백')를 보내야 함."""
    r = client.post(
        "/ai/v1/design-spec",
        json={"analysis": sample_analysis.model_dump(), "target_category": "가방"},
    )
    assert r.status_code == 422
