"""Stage 2 — 재창조 디자인 스펙 생성. 설계: Stage2.md.

흐름: analysis.json + (카테고리 or 자동) → 단일 호출로 후보 3개(safe/balanced/bold) → 코드 검증.
검증 실패 시 위반 내용을 피드백해 1회 재시도.
"""
from __future__ import annotations

import json
from typing import Any

from ai_pipeline.config import settings
from ai_pipeline.schemas.analysis import AnalysisResult
from ai_pipeline.schemas.design_spec import (
    CandidateList,
    candidate_list_json_schema,
    validate_portfolio,
)
from ai_pipeline.services import brand_assets, llm_client

# ---------------------------------------------------------------------------
# 프롬프트 조립
# ---------------------------------------------------------------------------

ROLE_AND_PRINCIPLES = """\
당신은 MCM의 업사이클링 아뜰리에 수석 디자이너다. 고객이 개인의 추억이 담긴 옷을 가져오면,
그 옷의 요소와 사연을 MCM 제품에 융합한 '단 하나의 재창조 디자인'을 설계한다.

# MCM 디자인 코드
{design_code}
"""

RECREATION_RULES = """\
# 재창조 원칙

## 개입 강도 스펙트럼 (intervention_level)
- 0: 컬러/무드만 이식  1: 패턴/그래픽 이식  2: 원단 부분 사용(패치·포켓·스트랩·트리밍)
- 3: 하이브리드(바디 패널 일부를 옷 원단으로)  4: 해체·재구성  5: 파생 굿즈(참·키링 등 카테고리 전환)

## 후보 3개 = 포트폴리오 (반드시 지킬 것)
- safe: intervention_level 1~2. 확실하게 제작 가능하고 브랜드 정합성이 명확한 안
- balanced: intervention_level 2~3. 임팩트와 안정의 균형
- bold: intervention_level 4~5. 과감한 재구성 또는 카테고리 전환 — 의외성 담당
- 세 후보는 재창조 방식이 서로 겹치지 않아야 한다.

## 창의성의 핵심 = 사연↔요소 매핑
- applied_elements의 reason에는 사연의 구체적 내용(인물·시간·기억)과 연결한 근거를 쓴다.
  나쁜 예: "패턴이 예뻐서". 좋은 예: "아버지가 20년간 매일 메던 어깨끈 자국을 스트랩 스티치로 남김".
- condition_cues(해짐·색바램·얼룩)는 숨길 결함이 아니라 살릴 디자인 요소다(비저블 멘딩).
  가능하면 후보 중 하나 이상은 흔적을 명시적으로 디자인에 반영한다.
- 방식 예시(패치, 패턴 융합, 컬러 이식, 자수 재현, 안감 활용, 참·키링 제작)는 영감용일 뿐,
  이 목록에 제한되지 않는다. 사연과 옷의 특성에 맞는 방식을 자유롭게 제안하라.

## 제약
- 실현 가능성: 공방에서 실제 제작 가능한 구성만. 원단이 녹아 섞이는 식의 물리적으로 불가능한 표현 금지.
- 브랜드 정합성: 위 디자인 코드를 벗어나지 않는다. 금지 사항 항목을 위반하는 안은 만들지 않는다.
- base_product는 반드시 제공된 레퍼런스의 product_id 중 하나를 쓴다.
  (예외: 레퍼런스 없는 자유 창작 모드가 명시된 경우에만 null — 해당 모드 지시를 따른다.)

## image_prompt 작성 규칙 (Stage 3 이미지 생성에 그대로 전달됨)
- 영문으로 작성. "Attach A onto B", "Replace X with Y" 형태의 구체적 편집 지시문.
- 마지막에 항상 포함: plain light-gray studio background, front view, product only, no props.
"""

MODE_FIXED = """\
# 이번 요청
고객이 목표 카테고리를 지정했다: **{category}**
세 후보 모두 이 카테고리 안에서 만들고, category_reason은 null로 둔다.
다양성 축은 재창조 방식(risk_profile)이다.
"""

MODE_AUTO = """\
# 이번 요청
고객이 카테고리를 지정하지 않았다 (AI 자동 제안 모드).
후보마다 사연·분위기에 가장 어울리는 MCM 카테고리를 직접 선정하고,
category_reason에 '왜 이 사연에 이 카테고리인가'를 1~2문장으로 쓴다.
다양성 축은 카테고리 + 재창조 방식이다. 세 후보의 카테고리가 모두 같아서는 안 된다.
"""

MODE_FIXED_NOREF = """\
# 이번 요청
고객이 목표 카테고리를 지정했다: **{category}** (악세사리 — 레퍼런스 없는 자유 창작 모드)
세 후보 모두 이 카테고리 안에서 만들고, category_reason은 null로 둔다.
이 카테고리는 제품 레퍼런스 이미지가 제공되지 않는다:
- base_product는 반드시 null로 둔다 (베이스 제품 없이 옷 원단·요소로 새로 만드는 창작물)
- 대신 system의 브랜드 디자인 코드(비세토스·시그니처 컬러·하드웨어)를 근거로 MCM 무드를 유지한다
- image_prompt에는 참조할 기존 제품이 없으므로 형태·소재·하드웨어를 스스로 구체적으로 서술한다
다양성 축은 재창조 방식(risk_profile)이다.
"""

RETRY_SUFFIX = """\

# 이전 시도 반려 사유 (모두 수정할 것)
{problems}
"""


def build_system_blocks() -> list[dict[str, Any]]:
    """system 프롬프트. [0] 역할+디자인 코드(캐시 대상) / [1] 재창조 원칙.

    ⚠️ 이 블록들에 요청마다 변하는 값(trace_id, 시각, 사용자 데이터)을 넣지 말 것 — 캐시 무효화.
    """
    return [
        {
            "type": "text",
            "text": ROLE_AND_PRINCIPLES.format(design_code=brand_assets.design_code_text()),
            "cache_control": {"type": "ephemeral"},
        },
        {"type": "text", "text": RECREATION_RULES},
    ]


def build_user_content(
    analysis: AnalysisResult,
    target_category: str | None,
    references: list[dict[str, Any]],
    retry_problems: list[str] | None = None,
    reference_free: bool = False,
) -> list[dict[str, Any]]:
    """user 메시지: 레퍼런스 이미지(+캡션) → analysis.json → 모드 지시."""
    content: list[dict[str, Any]] = []

    for entry in references:
        content.append({"type": "text", "text": brand_assets.reference_caption(entry)})
        content.append(brand_assets.image_block(entry))

    content.append(
        {
            "type": "text",
            "text": "# 고객 옷 분석 결과 (analysis.json)\n"
            + json.dumps(analysis.model_dump(), ensure_ascii=False, indent=2),
        }
    )

    if target_category and reference_free:
        mode_text = MODE_FIXED_NOREF.format(category=target_category)
    elif target_category:
        mode_text = MODE_FIXED.format(category=target_category)
    else:
        mode_text = MODE_AUTO
    if retry_problems:
        mode_text += RETRY_SUFFIX.format(problems="\n".join(f"- {p}" for p in retry_problems))
    content.append({"type": "text", "text": mode_text})

    return content


# ---------------------------------------------------------------------------
# 실행
# ---------------------------------------------------------------------------


def generate_design_specs(
    analysis: AnalysisResult | dict[str, Any],
    target_category: str | None = None,
    trace_id: str | None = None,
) -> CandidateList:
    """Stage 2 진입점. 후보 3개(CandidateList)를 반환한다.

    - target_category=None이면 자동 제안 모드
    - 포트폴리오 규칙 위반 시 위반 사유를 피드백해 1회 재시도, 그래도 실패면 예외
    """
    if isinstance(analysis, dict):
        analysis = AnalysisResult.model_validate(analysis)

    # 악세사리 서브는 레퍼런스-프리: 제품 사진 없이 디자인 코드(system 캐시)만으로 생성
    reference_free = target_category is not None and brand_assets.is_reference_free(target_category)
    if reference_free:
        references: list[dict[str, Any]] = []
    else:
        references = brand_assets.select_references(category=target_category)
        if not references and target_category is not None:
            # 해당 카테고리 레퍼런스가 아직 없으면(수집 진행 중) 전체에서 선별
            references = brand_assets.select_references(category=None)
        if not references:
            raise RuntimeError("레퍼런스 이미지가 없습니다 — data/_index.json 확인")

    schema = candidate_list_json_schema()
    system_blocks = build_system_blocks()

    problems: list[str] = []
    for _attempt in range(2):  # 최초 1회 + 재시도 1회
        content = build_user_content(
            analysis, target_category, references, problems or None,
            reference_free=reference_free,
        )
        raw = llm_client.structured_call(
            model=settings.llm_model,
            system_blocks=system_blocks,
            messages=[{"role": "user", "content": content}],
            schema=schema,
            stage="2",
            trace_id=trace_id,
        )
        result = CandidateList.model_validate(raw)
        problems = validate_portfolio(
            result, n_expected=settings.n_candidates, allow_null_base=reference_free
        )
        if not problems:
            return result

    raise RuntimeError(f"포트폴리오 규칙 위반이 재시도 후에도 남음: {problems}")
