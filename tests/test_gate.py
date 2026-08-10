"""검증 게이트(Harness 7.1) 수트 — structured_call을 mock해 키 없이 로직 검증."""
import json
from pathlib import Path

import pytest

from ai_pipeline.config import settings
from ai_pipeline.schemas.design_spec import DesignSpec
from ai_pipeline.schemas.verification import GateResult, clamp_score, gate_json_schema
from ai_pipeline.services import brand_assets, harness_gate
from ai_pipeline.services.stage3_concept import ConceptImage


def _spec(name: str = "Sunday Ride", profile: str = "safe", level: int = 2) -> DesignSpec:
    return DesignSpec.model_validate(
        {
            "concept_name": name,
            "category": "미니 레더백",
            "category_reason": None,
            "base_product": "dessau-cognac",
            "risk_profile": profile,
            "intervention_level": level,
            "creation_method": "데님 패치",
            "applied_elements": [
                {"from_element": "해진 소매", "to_element": "플랩 패치", "reason": "세월의 흔적"}
            ],
            "image_prompt": "Attach a worn denim patch onto the front flap.",
        }
    )


@pytest.fixture
def concepts(tmp_path) -> list[ConceptImage]:
    """가짜 컨셉 3장 (safe/balanced/bold) — 실제 파이프라인처럼 진짜 JPEG로 변환."""
    from PIL import Image

    src = settings.asset_root / brand_assets.load_index()[0]["file"]
    out = []
    for profile, level in (("safe", 2), ("balanced", 3), ("bold", 5)):
        p = tmp_path / f"c_{profile}.jpg"
        Image.open(src).convert("RGB").save(p, "JPEG")
        out.append(
            ConceptImage(spec=_spec(profile=profile, level=level), image_path=p,
                         trace_id="t", reference_used=None)
        )
    return out


def _mock_scores(monkeypatch, results: dict[str, dict]):
    """risk_profile → GateResult dict 매핑으로 structured_call을 대체."""
    calls = {"n": 0}

    def fake_call(*, model, system_blocks, messages, schema, stage, max_tokens=0, effort="x", trace_id=None):
        calls["n"] += 1
        assert model == settings.gate_model
        assert effort is None, "Haiku에는 effort를 넣으면 안 됨 (400)"
        text = messages[0]["content"][0]["text"]
        for profile, result in results.items():
            if f"({profile}," in text:
                return result
        raise AssertionError(f"프로파일 매칭 실패: {text[:100]}")

    monkeypatch.setattr(harness_gate.llm_client, "structured_call", fake_call)
    return calls


# ---------------------------------------------------------------------------
# 스키마
# ---------------------------------------------------------------------------


def test_gate_schema_constraints():
    schema = json.dumps(gate_json_schema())
    assert '"additionalProperties": false' in schema
    for banned in ('"minimum"', '"maximum"', '"minItems"'):
        assert banned not in schema


def test_clamp_score():
    assert clamp_score(GateResult(passed=True, score=150, fail_reasons=[])).score == 100
    assert clamp_score(GateResult(passed=False, score=-5, fail_reasons=["x"])).score == 0
    assert clamp_score(GateResult(passed=True, score=87, fail_reasons=[])).score == 87


# ---------------------------------------------------------------------------
# 프롬프트 조립
# ---------------------------------------------------------------------------


def test_system_blocks_cached_and_criteria():
    blocks = harness_gate.build_system_blocks()
    assert blocks[0]["cache_control"] == {"type": "ephemeral"}
    text = blocks[0]["text"]
    assert "비세토스" in text, "브랜드 디자인 코드 포함"
    assert "실현 가능성" in text, "Stage2.md 4절 기준 포함"
    assert "감점 사유가 아니다" in text, "bold 후보 관대 채점 규칙"


def test_user_content_includes_spec_and_image(concepts):
    content = harness_gate.build_user_content(concepts[0].spec, concepts[0].image_path)
    assert "해진 소매 → 플랩 패치" in content[0]["text"]
    assert content[1]["type"] == "image"
    assert content[1]["source"]["media_type"] == "image/jpeg"


# ---------------------------------------------------------------------------
# 게이트 동작
# ---------------------------------------------------------------------------


def test_gate_concepts_sorts_by_score(monkeypatch, concepts):
    _mock_scores(monkeypatch, {
        "safe": {"passed": True, "score": 70, "fail_reasons": []},
        "balanced": {"passed": True, "score": 95, "fail_reasons": []},
        "bold": {"passed": False, "score": 40, "fail_reasons": ["왜곡"]},
    })
    gated = harness_gate.gate_concepts(concepts)
    assert [g.gate.score for g in gated] == [95, 70, 40], "점수 내림차순"


def test_gate_with_retry_passes_filter(monkeypatch, concepts):
    """일부 통과 → 통과 컷만 제시, 재생성 없음."""
    _mock_scores(monkeypatch, {
        "safe": {"passed": True, "score": 80, "fail_reasons": []},
        "balanced": {"passed": False, "score": 50, "fail_reasons": ["스펙 미반영"]},
        "bold": {"passed": True, "score": 88, "fail_reasons": []},
    })
    outcome = harness_gate.gate_with_retry(concepts, regenerate=lambda specs: pytest.fail("재생성되면 안 됨"))
    assert not outcome.all_failed and not outcome.regenerated
    assert [g.concept.spec.risk_profile for g in outcome.candidates] == ["bold", "safe"]


def test_gate_with_retry_regenerates_once_on_all_fail(monkeypatch, concepts):
    """전원 불합격 → 재생성 1회 → 통과."""
    state = {"round": 0}

    def fake_call(*, messages, **kw):
        # 1라운드: 전원 불합격 / 2라운드: 전원 합격
        if state["round"] == 0:
            return {"passed": False, "score": 30, "fail_reasons": ["패턴 미반영"]}
        return {"passed": True, "score": 85, "fail_reasons": []}

    monkeypatch.setattr(harness_gate.llm_client, "structured_call", fake_call)

    def regenerate(specs):
        state["round"] = 1
        for s in specs:
            assert "패턴 미반영" in s.image_prompt, "fail_reasons가 재생성 프롬프트에 피드백돼야 함"
        return concepts  # 같은 이미지 재사용 (테스트)

    outcome = harness_gate.gate_with_retry(concepts, regenerate=regenerate)
    assert outcome.regenerated and not outcome.all_failed
    assert len(outcome.candidates) == 3


def test_gate_with_retry_all_fail_fallback(monkeypatch, concepts):
    """재생성 후에도 전원 불합격 → 최고점 순 그대로 제시 + all_failed 플래그."""
    monkeypatch.setattr(
        harness_gate.llm_client, "structured_call",
        lambda **kw: {"passed": False, "score": 45, "fail_reasons": ["브랜드 코드 위반"]},
    )
    regen_calls = {"n": 0}

    def regenerate(specs):
        regen_calls["n"] += 1
        return concepts

    outcome = harness_gate.gate_with_retry(concepts, regenerate=regenerate)
    assert outcome.all_failed and outcome.regenerated
    assert regen_calls["n"] == 1, "재생성은 정확히 1회 (무한 루프 방지)"
    assert len(outcome.candidates) == 3, "탈락시키지 않고 전부 제시 (사용자 선택권 유지)"


# ---------------------------------------------------------------------------
# 실호출 스모크 (ANTHROPIC_API_KEY 있을 때 — Haiku라 소액)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not settings.anthropic_api_key, reason="ANTHROPIC_API_KEY 없음")
def test_score_concept_smoke(concepts):
    result = harness_gate.score_concept(concepts[0])
    assert isinstance(result.passed, bool)
    assert 0 <= result.score <= 100
    # 가방 원본 사진을 '패치 반영 결과'라고 주장하는 스펙이므로, 스펙 미반영을 잡아낼 가능성이 높음
    print(f"\n게이트 스모크: passed={result.passed}, score={result.score}, reasons={result.fail_reasons}")
