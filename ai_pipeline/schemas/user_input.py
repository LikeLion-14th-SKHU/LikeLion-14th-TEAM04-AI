"""Stage 1 입력(user_input) 스키마 — ⚠️ 시작점 초안.

소유: Stage 1 담당 (팀원). 이 파일은 AI_Dev_PipeLine.md Stage 1 절의 토글 정의를
코드로 옮긴 출발점이며, 최종 확정은 Stage 1 담당자가 한다.

계약 상대가 analysis.py와 다르다:
- analysis.py  → Stage 1 ↔ Stage 2 (창현) 사이의 계약
- user_input.py → Stage 1 ↔ 프론트엔드/백엔드 사이의 계약
  (아래 enum들은 토글 UI의 선택지와 1:1로 일치해야 한다 — 값 변경 시 프론트와 협의)

참고: 이 스키마는 사용자 입력 검증용이라 Structured Outputs 제약과 무관하다.
max_length 같은 수치 제약을 자유롭게 써도 된다 (LLM 출력 스키마인 analysis/design_spec과 다른 점).
"""
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

# ---------------------------------------------------------------------------
# 토글 선택지 (= 프론트 UI와 1:1)
# ---------------------------------------------------------------------------

MainCategory = Literal["상의", "하의", "아우터", "원피스·스커트", "기타"]

# 대분류 → 중분류 목록. ⚠️ 문서에는 상의 예시만 있음 — 나머지는 초안이니 UI 팀과 확정할 것
SUB_CATEGORIES: dict[str, list[str]] = {
    "상의": ["후드티", "티셔츠", "셔츠", "니트", "맨투맨", "블라우스"],
    "하의": ["청바지", "슬랙스", "반바지", "트레이닝 팬츠"],
    "아우터": ["자켓", "코트", "패딩", "가디건", "점퍼"],
    "원피스·스커트": ["원피스", "스커트"],
    "기타": [],  # 기타는 중분류 자유 입력 허용
}

Material = Literal["면", "데님", "울·니트", "가죽", "폴리", "모르겠어요"]

Condition = Literal["해짐", "색 바램", "얼룩", "늘어남", "새것 같음"]

STORY_MAX_LENGTH = 500


# ---------------------------------------------------------------------------
# 스키마
# ---------------------------------------------------------------------------


class ClothingCategory(BaseModel):
    model_config = ConfigDict(extra="forbid")

    main: MainCategory
    sub: str  # SUB_CATEGORIES[main] 중 하나 (기타는 자유 입력)

    @model_validator(mode="after")
    def sub_must_belong_to_main(self) -> "ClothingCategory":
        allowed = SUB_CATEGORIES[self.main]
        if allowed and self.sub not in allowed:
            raise ValueError(f"'{self.main}'의 중분류가 아님: '{self.sub}' (허용: {allowed})")
        if not allowed and not self.sub.strip():
            raise ValueError("기타 카테고리는 중분류를 직접 입력해야 함")
        return self


class UserInput(BaseModel):
    """Stage 1(/ai/v1/narrative)의 요청 본문 중 옷 정보 + 사연.

    옷 '사진'은 여기 포함되지 않는다 — 별도 필드(base64/file)로 API 계약에서 다룬다.
    """
    model_config = ConfigDict(extra="forbid")

    category: ClothingCategory
    material: Material
    condition: list[Condition] = Field(default_factory=list)  # 선택 항목, 복수 선택 가능
    story: str = Field(min_length=1, max_length=STORY_MAX_LENGTH)  # 사연 원문 (story_raw로 서버 보관)

    @property
    def material_unknown(self) -> bool:
        """'모르겠어요' 선택 여부 — True면 Stage 1이 재질 판정을 Vision 추정에 위임한다.

        (analysis.py의 재질 병합 규칙: 사용자 값 우선, '모르겠어요'일 때만 Vision 값 채택)
        """
        return self.material == "모르겠어요"
