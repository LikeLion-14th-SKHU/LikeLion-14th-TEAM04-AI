"""Stage 1 — 옷 이미지 및 사용자 사연 분석 서비스.

수행하는 일:
- 사용자 입력(옷 사진 + UserInput 토글 및 사연)을 수신
- Claude Sonnet (멀티모달)을 호출하여 이미지의 시각적 요소(컬러, 패턴, 추정 재질, 해짐 등 흔적)와
  사연의 감성/배경을 종합적으로 추론 및 정리
- Stage 1 ↔ Stage 2 계약 스키마인 AnalysisResult 객체 반환
"""
from __future__ import annotations

import base64
from pathlib import Path
from typing import Any

from ai_pipeline.config import settings
from ai_pipeline.schemas.analysis import AnalysisResult
from ai_pipeline.schemas.user_input import UserInput
from ai_pipeline.services import llm_client

STAGE1_SYSTEM_PROMPT = """\
당신은 MCM 업사이클링 브랜드의 수석 패션 컨설턴트이자 스토리 에디터입니다.
고객이 제출한 [옷 사진]과 [옷 정보 및 사연(UserInput)]을 정밀하게 분석하여,
MCM 업사이클링 디자이너(Stage 2)가 제품 설계에 사용할 수 있는 구조화된 분석 결과를 생성합니다.

# 분석 지침 및 원칙

## 1. Visual (시각 요소 분석)
- color_palette: 옷 이미지 및 분위기에서 추출한 주요 HEX 컬러 코드 2~4개.
- pattern: 시각적 패턴 (예: "무지", "체크", "스트라이프", "플로럴", "프린팅" 등).
- material_user: 고객이 토글로 선택한 재질 (user_input.material) 그대로 기록.
- material_estimate: 옷 사진을 보고 Vision으로 추정한 원단 재질 (예: "데님", "면", "울", "가죽", "폴리에스터" 등).
- material_final: 병합 규칙 적용.
  * material_user가 "선택안함"인 경우 -> material_estimate 채택
  * material_user가 지정되어 있는 경우 -> material_user 채택
- condition_cues: 사진과 사연에서 포착되는 해짐, 색 바램, 얼룩, 늘어남, 마모 자국 등 세월의 흔적 (list of str).
  * 이 흔적들은 훗날 '비저블 멘딩(Visible Mending)'의 중요한 디자인 근거가 됩니다.
- vibe_keywords: 이미지와 사연이 전하는 전체적인 감성/분위기 키워드 3~5개 (예: ["빈티지", "차분함", "추억"]).

## 2. Story (사연 정리 및 깊이 있는 해석)
- polished: 원문의 어투와 뉘앙스를 유지한 채 맞춤법·문장만 정리한 공유용 텍스트. 요약·축약 금지 — 긴 사연도 전문을 유지한다 (재해석·압축은 interpretation에서만).
- interpretation: 사연 속 인물, 시간, 기억이 이 옷과 가지는 관계 및 의미를 깊이 있게 풀어낸 내부용 해석 (2~3문장). Stage 2 디자이너가 핵심적으로 참고함.
- emotion_keywords: 사연에 녹아있는 감정 키워드 2~4개 (예: ["그리움", "따뜻함", "감사"]).

## 3. Edition & Certificate (에디션명 및 보증서)
- edition_name_candidates: 사연과 옷의 가치를 담은 단 하나뿐인 업사이클링 에디션 명칭 후보 3개 (예: ["Sunday Ride", "아버지의 주말", "Denim Years"]).
- certificate_text: 완성된 업사이클링 제품의 보증서에 각인될 정갈하고 품격 있는 1문장의 보증 문구.
"""


def _build_image_block(image_path: str | Path) -> dict[str, Any]:
    """이미지 파일을 읽어 Anthropic API용 base64 content block으로 변환."""
    path = Path(image_path)
    if not path.is_file():
        raise FileNotFoundError(f"이미지 파일을 찾을 수 없습니다: {path}")

    ext = path.suffix.lower().lstrip(".")
    if ext in ("jpg", "jpeg"):
        media_type = "image/jpeg"
    elif ext == "png":
        media_type = "image/png"
    elif ext == "webp":
        media_type = "image/webp"
    elif ext == "gif":
        media_type = "image/gif"
    else:
        media_type = "image/jpeg"

    data = base64.b64encode(path.read_bytes()).decode("utf-8")
    return {
        "type": "image",
        "source": {
            "type": "base64",
            "media_type": media_type,
            "data": data,
        },
    }


def analyze(
    image_path: str | Path | None,
    user_input: UserInput,
    trace_id: str | None = None,
) -> AnalysisResult:
    """옷 사진 + UserInput(토글 선택 + 사연 원문) -> Claude Sonnet 분석 -> AnalysisResult 반환."""
    system_blocks = [
        {
            "type": "text",
            "text": STAGE1_SYSTEM_PROMPT,
            "cache_control": {"type": "ephemeral"},
        }
    ]

    user_content: list[dict[str, Any]] = []

    # 1. 이미지 블록 추가 (이미지가 제공된 경우)
    if image_path:
        user_content.append(_build_image_block(image_path))

    # 2. UserInput 정보를 텍스트 블록으로 정리하여 추가
    input_text = (
        f"# 고객 입력 데이터\n"
        f"- 카테고리: {user_input.category.main} > {user_input.category.sub}\n"
        f"- 재질(사용자 선택): {user_input.material}\n"
        f"- 상태/흔적: {', '.join(user_input.condition) if user_input.condition else '특이사항 없음'}\n\n"
        f"# 사연 원문 (story_raw)\n"
        f"\"{user_input.story}\"\n"
    )
    user_content.append({"type": "text", "text": input_text})

    # 3. LLM structured call 호출
    schema = AnalysisResult.model_json_schema()
    raw = llm_client.structured_call(
        model=settings.llm_model,
        system_blocks=system_blocks,
        messages=[{"role": "user", "content": user_content}],
        schema=schema,
        stage="1",
        trace_id=trace_id,
    )

    return AnalysisResult.model_validate(raw)
