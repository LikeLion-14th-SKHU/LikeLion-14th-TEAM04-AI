"""Stage 1 출력(analysis.json) 계약.

⚠️ 이 파일은 Stage 1(팀원) ↔ Stage 2(창현)의 공유 인터페이스다.
필드를 바꾸려면 반드시 상대 담당자와 협의할 것. 원본 정의: AI_Dev_PipeLine.md Stage 1 절.
Stage 2는 이 스키마를 '입력 검증'에 사용하고, Stage 1은 '출력 스키마'로 사용한다.
"""
from pydantic import BaseModel, ConfigDict


class Visual(BaseModel):
    model_config = ConfigDict(extra="forbid")

    color_palette: list[str]          # HEX 코드
    pattern: str                      # 체크 / 스트라이프 / 무지 등
    material_user: str                # 사용자 토글 선택값
    material_estimate: str            # Vision 추정값
    material_final: str               # 병합 규칙 적용 결과
    condition_cues: list[str]         # 해짐·색바램 등 — Stage 2의 '흔적 살리기' 근거
    vibe_keywords: list[str]


class Story(BaseModel):
    model_config = ConfigDict(extra="forbid")

    polished: str                     # 공유용 — 원문 어투 유지, 정리만
    interpretation: str               # 내부용 해석 (2~3문장) — Stage 2가 주로 참조
    emotion_keywords: list[str]


class AnalysisResult(BaseModel):
    """Stage 1 → Stage 2/5 로 전달되는 분석 결과."""
    model_config = ConfigDict(extra="forbid")

    visual: Visual
    story: Story
    edition_name_candidates: list[str]
    certificate_text: str
