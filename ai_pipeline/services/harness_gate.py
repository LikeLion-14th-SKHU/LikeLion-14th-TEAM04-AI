"""Harness 7.1 — 검증 게이트 (Stage 3 직후, 사용자 선택 전).

Haiku 4.5가 컨셉 이미지 n장을 병렬 채점한다:
  ① design_spec의 applied_elements가 이미지에 반영되었는가
  ② MCM 브랜드 코드(비세토스·시그니처 컬러 등)를 벗어나지 않았는가
  ③ 심각한 시각적 결함(왜곡·아티팩트)이 없는가
  ④ 공방에서 실제 제작 가능해 보이는가 (Stage2.md 4절)
  ⑤ 로고 판독성 — 정방향 로고가 'MCM'으로 정확히 읽히는가 ('MOM' 뭉개짐 불합격)

동작 (AI_Dev_PipeLine.md 7.1):
- 불합격 컷 제외, 통과 컷 점수순 정렬 → 사용자에게는 통과 컷만 제시
- 전원 불합격 시에만 fail_reasons를 피드백해 재생성 1회
- 그래도 전원 불합격이면 최고 점수순으로 그대로 제시하고 로그에 기록

주의: Haiku 4.5는 output_config.effort 미지원 → structured_call(effort=None) 필수.
"""
from __future__ import annotations

import base64
import mimetypes
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from ai_pipeline.config import settings
from ai_pipeline.schemas.design_spec import DesignSpec
from ai_pipeline.schemas.verification import GateResult, clamp_score, gate_json_schema
from ai_pipeline.services import brand_assets, llm_client
from ai_pipeline.services.stage3_concept import ConceptImage

GATE_SYSTEM_PROMPT = """\
당신은 MCM 업사이클링 아뜰리에의 품질 검수자다.
디자이너가 만든 재창조 컨셉 이미지가 스펙과 브랜드 기준을 충족하는지 채점한다.

# MCM 디자인 코드 (브랜드 정합성 판정 기준)
{design_code}

# 평가 기준 (하나라도 심각하게 미달이면 불합격)
1. 스펙 반영: design_spec의 applied_elements의 **의도가 이미지에서 읽히는가**.
   문구의 세부(정확한 위치·비율 수치·색감 뉘앙스)가 조금 다르게 구현된 것은 정상 범위 —
   해당 요소가 아예 보이지 않거나 정반대로 구현된 경우만 미달.
2. 브랜드 정합성: 위 디자인 코드를 벗어나지 않는가 (특히 '금지 사항' 위반 여부)
3. 시각 품질: 심각한 왜곡·아티팩트·비현실적 형태가 없는가
4. 실현 가능성: 공방에서 실제 제작 가능한 구성으로 보이는가 (원단이 녹아 섞인 듯한 표현 등은 불합격)
5. 로고 판독성: 이미지에서 **가장 크게 보이는 로고**(금속 플레이트, 대형 레터링)가
   'MCM'으로 읽히면 합격. 그것이 명백히 다른 글자로 붕괴된 경우만 불합격.
   - 원단 모노그램의 작은 반복 레터링은 실제 제품 사진에서도 흐릿하다 — 판정 대상이 아니다.
   - 비세토스는 한 줄 걸러 로고가 뒤집혀 배치된다 — 뒤집힌 행은 판정하지 않는다.

# 판정 시 공통 주의 (과잉 판정 금지)
- '심각하게 미달'일 때만 불합격이다. 개선 여지가 있는 정도는 감점으로 반영하되 passed=true.
- 디자인 코드의 세부 수치(로렐 잎 개수 등)는 배경 지식이다 — 잎 개수를 세어 감점하지 않는다.
- 블랙 비세토스 같은 톤온톤 컬러웨이는 공식 변주다 — 패턴 콘트라스트가 낮아 보여도 정상.
- fail_reasons는 한국어로 쓴다.

# 채점 규칙
- passed: 다섯 기준을 모두 충족하면 true
- score: 0~100 정수. 90+ 탁월 / 70~89 양호 / 50~69 미흡 / 50 미만 심각
- fail_reasons: 불합격 시 구체적 사유 (재생성 프롬프트에 피드백되므로, 무엇을 어떻게 고쳐야 하는지 알 수 있게).
  합격이면 빈 배열.
- 대담한 디자인(재구성·카테고리 전환) 자체는 감점 사유가 아니다 — 네 기준 위반만 본다.
"""


@dataclass
class GatedConcept:
    """게이트를 거친 컨셉 1건 — 프론트 후보 카드의 단위."""
    concept: ConceptImage
    gate: GateResult


@dataclass
class GateOutcome:
    """게이트 전체 결과."""
    candidates: list[GatedConcept]   # 사용자에게 제시할 목록 (점수 내림차순)
    all_failed: bool                 # True면 candidates는 '최고점 컷 그대로 제시' 모드 (로그 확인 필요)
    regenerated: bool                # 전원 불합격으로 재생성이 발생했는가


def _image_block(path: Path) -> dict[str, Any]:
    mime = mimetypes.guess_type(path.name)[0] or "image/jpeg"
    data = base64.standard_b64encode(path.read_bytes()).decode("utf-8")
    return {"type": "image", "source": {"type": "base64", "media_type": mime, "data": data}}


def build_system_blocks() -> list[dict[str, Any]]:
    """게이트 system 프롬프트 — n장 채점 동안 동일하므로 캐시 대상."""
    return [
        {
            "type": "text",
            "text": GATE_SYSTEM_PROMPT.format(design_code=brand_assets.design_code_text()),
            "cache_control": {"type": "ephemeral"},
        }
    ]


def build_user_content(spec: DesignSpec, image_path: Path) -> list[dict[str, Any]]:
    applied = "\n".join(
        f"- {el.from_element} → {el.to_element} (근거: {el.reason})" for el in spec.applied_elements
    )
    spec_text = (
        f"# 검수 대상 design_spec\n"
        f"- 컨셉: {spec.concept_name} ({spec.risk_profile}, 개입 강도 Lv{spec.intervention_level})\n"
        f"- 카테고리: {spec.category} / 베이스 제품: {spec.base_product}\n"
        f"- 재창조 방식: {spec.creation_method}\n"
        f"- applied_elements:\n{applied}\n\n"
        f"위 스펙으로 생성된 아래 컨셉 이미지를 채점하라."
    )
    return [{"type": "text", "text": spec_text}, _image_block(image_path)]


def score_concept(concept: ConceptImage, trace_id: str | None = None) -> GateResult:
    """컨셉 1장 채점 — Haiku 1회 호출."""
    raw = llm_client.structured_call(
        model=settings.gate_model,
        system_blocks=build_system_blocks(),
        messages=[{"role": "user", "content": build_user_content(concept.spec, concept.image_path)}],
        schema=gate_json_schema(),
        stage="gate",
        max_tokens=1024,
        effort=None,          # ⚠️ Haiku 4.5는 effort 미지원 — 넣으면 400
        trace_id=trace_id,
    )
    return clamp_score(GateResult.model_validate(raw))


def gate_concepts(concepts: list[ConceptImage]) -> list[GatedConcept]:
    """n장 병렬 채점 → 점수 내림차순 정렬 (필터링은 하지 않음)."""
    trace_id = str(uuid.uuid4())
    with ThreadPoolExecutor(max_workers=min(4, len(concepts))) as pool:
        results = list(pool.map(lambda c: score_concept(c, trace_id=trace_id), concepts))
    gated = [GatedConcept(concept=c, gate=g) for c, g in zip(concepts, results)]
    return sorted(gated, key=lambda g: g.gate.score, reverse=True)


def feedback_specs(gated: list[GatedConcept]) -> list[DesignSpec]:
    """전원 불합격 시 재생성용 — fail_reasons를 image_prompt에 반영한 스펙 사본."""
    specs = []
    for g in gated:
        reasons = "; ".join(g.gate.fail_reasons) or "quality issues"
        new_prompt = (
            f"{g.concept.spec.image_prompt}\n"
            f"IMPORTANT — the previous attempt was rejected for: {reasons}. Fix these issues."
        )
        specs.append(g.concept.spec.model_copy(update={"image_prompt": new_prompt}))
    return specs


def gate_with_retry(
    concepts: list[ConceptImage],
    regenerate: Callable[[list[DesignSpec]], list[ConceptImage]] | None = None,
) -> GateOutcome:
    """게이트 본체.

    - 통과 컷이 하나라도 있으면: 통과 컷만 점수순으로 제시
    - 전원 불합격 + regenerate 제공 시: fail_reasons 피드백으로 재생성 1회 후 재채점
    - 그래도 전원 불합격: 전체를 점수순으로 제시 (all_failed=True — 호출부는 로그·표시에 반영)

    regenerate는 보통 stage3의 재생성 함수를 부분 적용해 넘긴다 (테스트에서는 가짜 주입).
    """
    gated = gate_concepts(concepts)
    passed = [g for g in gated if g.gate.passed]
    if passed:
        return GateOutcome(candidates=passed, all_failed=False, regenerated=False)

    regenerated = False
    if regenerate is not None:
        regenerated = True
        new_concepts = regenerate(feedback_specs(gated))
        gated = gate_concepts(new_concepts)
        passed = [g for g in gated if g.gate.passed]
        if passed:
            return GateOutcome(candidates=passed, all_failed=False, regenerated=True)

    # 최후: 최고 점수 컷들을 그대로 제시 (사용자 선택권 유지) — all_failed 플래그로 추적
    return GateOutcome(candidates=gated, all_failed=True, regenerated=regenerated)
