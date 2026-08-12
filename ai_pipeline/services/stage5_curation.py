"""Stage 5 — 럭셔리 큐레이션 서비스.

고객의 사연(analysis.json)과 재창조 결과(design_spec)를 바탕으로
MCM 카탈로그에서 어울리는 기존 제품 2~3개를 선별하고 서사 기반 큐레이션을 제공한다.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ai_pipeline.config import settings
from ai_pipeline.schemas.analysis import AnalysisResult
from ai_pipeline.schemas.curation import (
    CurationResult,
    curation_json_schema,
    validate_curation,
)
from ai_pipeline.schemas.design_spec import DesignSpec
from ai_pipeline.services import llm_client

ROLE_AND_CATALOG_PROMPT = """\
당신은 MCM의 럭셔리 큐레이터 및 에디토리얼 디렉터다.
고객이 소중한 추억이 담긴 옷을 가지고 아뜰리에를 방문하여 단 하나의 '재창조 디자인'을 완성했다.
당신의 역할은 고객의 사연과 완성된 재창조 디자인을 바탕으로,
현재 MCM의 기존 럭셔리 컬렉션 중 함께 곁들이거나 동행하기에 가장 잘 어울리는 제품 2~3개를 큐레이션해주는 것이다.

# MCM 추천 대상 카탈로그
아래 목록에 존재하는 제품(product_id)만 추천할 수 있다. 카탈로그 외의 제품을 지어내거나 추측해서 추천하는 것은 엄격히 금지된다.

{catalog_json}
"""

CURATION_INSTRUCTIONS = """\
# 큐레이션 작성 원칙

1. **추천 제품 개수**: 반드시 카탈로그에서 2개 또는 3개의 제품을 선별하라.
2. **재창조 베이스 제품 제외**: 이미 재창조 디자인(design_spec)에 베이스 제품으로 사용된 product_id는 추천 목록에서 반드시 제외하라.
3. **서사 중심의 큐레이션 이유 (reason)**:
   - "디자인이 예뻐서", "좋은 가방이라서" 같은 단순 제품 스펙 나열 금지.
   - 고객 사연의 내부 해석(story.interpretation) 및 구체적 요소(인물, 시간, 장소, 추억)와 MCM 제품의 헤리티지/설명을 깊이 있게 연결하여 2~3문장으로 서술하라.
4. **한 줄 카피 (tagline)**:
   - 사연의 핵심 감성과 제품의 어우러짐을 나타내는 정갈한 한 줄 카피 (25자 내외).
   - 예시: "아버지와의 주말을 담은 여행 가방", "바닷가 웃음소리를 기억하는 세련된 쇼퍼"
"""

RETRY_SUFFIX = """\
# 이전 시도 반려 사유 (모두 수정할 것)
{problems}
"""


def load_catalog() -> dict[str, Any]:
    """mcm_catalog.json 파일 로드."""
    catalog_path = settings.mcm_catalog_path
    if not catalog_path.exists():
        raise FileNotFoundError(f"카탈로그 파일이 없습니다: {catalog_path}")
    return json.loads(catalog_path.read_text(encoding="utf-8"))


def build_system_blocks(catalog_data: dict[str, Any]) -> list[dict[str, Any]]:
    """system 프롬프트 조립.

    ⚠️ 요청마다 변하는 값(trace_id, 타임스탬프)을 주입하지 말 것 (프롬프트 캐시 유지용).
    """
    catalog_json_str = json.dumps(catalog_data, ensure_ascii=False, indent=2)
    return [
        {
            "type": "text",
            "text": ROLE_AND_CATALOG_PROMPT.format(catalog_json=catalog_json_str),
            "cache_control": {"type": "ephemeral"},
        },
        {"type": "text", "text": CURATION_INSTRUCTIONS},
    ]


def build_user_content(
    analysis: AnalysisResult,
    design_spec: DesignSpec | dict[str, Any],
    retry_problems: list[str] | None = None,
) -> list[dict[str, Any]]:
    """user 메시지 구성: analysis 사연 정보 + 선택된 design_spec 요약."""
    ds_dict = design_spec.model_dump() if isinstance(design_spec, DesignSpec) else design_spec

    user_text = f"""\
# 고객 사연 및 분석 결과 (analysis.json)
- 정돈된 사연: {analysis.story.polished}
- 사연 내부 해석 (주요 참조): {analysis.story.interpretation}
- 옷의 재질: {analysis.visual.material_final}
- 세월의 흔적: {', '.join(analysis.visual.condition_cues) or '없음'}
- 감정 키워드: {', '.join(analysis.story.emotion_keywords)}
- 분위기 키워드: {', '.join(analysis.visual.vibe_keywords)}
- 에디션 명칭 후보: {', '.join(analysis.edition_name_candidates)}

# 고객이 최종 선택한 재창조 디자인 스펙 (design_spec)
- 컨셉명: {ds_dict.get('concept_name')}
- 카테고리: {ds_dict.get('category')}
- 베이스 제품 (추천에서 제외할 product_id): {ds_dict.get('base_product')}
- 재창조 방식: {ds_dict.get('creation_method')}
- 적용된 사연 요소: {json.dumps(ds_dict.get('applied_elements', []), ensure_ascii=False)}

위 사연과 재창조 디자인을 바탕으로 MCM 카탈로그에서 어울리는 기존 제품 2~3개를 큐레이션해주세요.
"""

    if retry_problems:
        user_text += "\n" + RETRY_SUFFIX.format(problems="\n".join(f"- {p}" for p in retry_problems))

    return [{"type": "text", "text": user_text}]


def generate_curation(
    analysis: AnalysisResult | dict[str, Any],
    design_spec: DesignSpec | dict[str, Any],
    trace_id: str | None = None,
) -> CurationResult:
    """Stage 5 진입점. 큐레이션 결과(CurationResult)를 반환한다.

    - 규칙 위반 시 피드백 후 1회 재시도, 그래도 실패면 예외 발생
    """
    if isinstance(analysis, dict):
        analysis = AnalysisResult.model_validate(analysis)
    if isinstance(design_spec, dict):
        design_spec = DesignSpec.model_validate(design_spec)

    catalog_data = load_catalog()
    products = catalog_data.get("products", [])
    valid_ids = [p["product_id"] for p in products]

    if not valid_ids:
        raise RuntimeError("카탈로그에 유효한 product_id가 없습니다.")

    schema = curation_json_schema(valid_ids)
    system_blocks = build_system_blocks(catalog_data)
    base_product = design_spec.base_product

    problems: list[str] = []
    for _attempt in range(2):  # 최초 1회 + 재시도 1회
        content = build_user_content(analysis, design_spec, problems or None)
        raw = llm_client.structured_call(
            model=settings.llm_model,
            system_blocks=system_blocks,
            messages=[{"role": "user", "content": content}],
            schema=schema,
            stage="5",
            trace_id=trace_id,
        )
        result = CurationResult.model_validate(raw)
        problems = validate_curation(result, valid_ids, base_product=base_product)
        if not problems:
            return result

    raise RuntimeError(f"큐레이션 규칙 위반이 재시도 후에도 남음: {problems}")
