"""Stage 1 입력(user_input) 스키마 — ✅ 개편본 (2026-08-18 팀 확정).

소유: Stage 1 담당 (팀원). 아래 토글 선택지는 프론트 UI와 1:1로 확정된 계약이다.
값을 바꾸려면 프론트엔드 팀과 재협의 필수.

계약 상대가 analysis.py와 다르다:
- analysis.py  → Stage 1 ↔ Stage 2 (창현) 사이의 계약
- user_input.py → Stage 1 ↔ 프론트엔드/백엔드 사이의 계약

⚠️ 2026-08-18 개편 내용 (Stage 1 담당자 확인 필요):
- 대분류가 의류/가방/악세사리 → 상의/하의/원피스/아우터 로 재편.
  (기존 의류/가방/악세사리 계층은 '재창조 목표 카테고리'로 이동 — brand_assets.RECREATION_TAXONOMY)
- 서브에 '직접입력' 추가: sub="직접입력"이면 sub_custom(자유 텍스트)이 필수.
  Stage 1 프롬프트에서 카테고리를 읽을 때는 resolved_sub를 쓸 것.

참고: 이 스키마는 사용자 입력 검증용이라 Structured Outputs 제약과 무관하다.
max_length 같은 수치 제약을 자유롭게 써도 된다.
"""
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

# ---------------------------------------------------------------------------
# 토글 선택지 (= 프론트 UI와 1:1, 2026-08-18 확정)
# ---------------------------------------------------------------------------

MainCategory = Literal["상의", "하의", "원피스", "아우터"]

CUSTOM_SUB = "직접입력"   # 이 값이면 sub_custom(자유 텍스트)이 필수

SUB_CATEGORIES: dict[str, list[str]] = {
    "상의": ["티셔츠", "셔츠", "블라우스", "니트", "맨투맨", "후드티", CUSTOM_SUB],
    "하의": ["청바지", "슬랙스", "반바지", "스커트", "트레이닝팬츠", CUSTOM_SUB],
    "원피스": ["미니원피스", "미디원피스", "롱원피스", "점프수트", CUSTOM_SUB],
    "아우터": ["자켓", "코트", "패딩", "가디건", "바람막이", CUSTOM_SUB],
}

Material = Literal["데님", "가죽", "니트", "울", "면", "린넨", "벨벳", "레이스", "선택안함"]

# 상태 토글은 프론트 확정 통보에 없었음 — 기존 정의 유지 (변경 시 여기도 확정 반영)
Condition = Literal["해짐", "색 바램", "얼룩", "늘어남", "새것 같음"]

STORY_MAX_LENGTH = 500
SUB_CUSTOM_MAX_LENGTH = 20

MATERIAL_UNKNOWN = "선택안함"   # 이 값이면 Stage 1이 재질 판정을 Vision 추정에 위임


# ---------------------------------------------------------------------------
# 스키마
# ---------------------------------------------------------------------------


class ClothingCategory(BaseModel):
    model_config = ConfigDict(extra="forbid")

    main: MainCategory
    sub: str                                # SUB_CATEGORIES[main] 중 하나 ("직접입력" 포함)
    sub_custom: str | None = Field(         # sub="직접입력"일 때만 사용 (그 외엔 보내지 말 것)
        default=None, min_length=1, max_length=SUB_CUSTOM_MAX_LENGTH
    )

    @model_validator(mode="after")
    def sub_must_belong_to_main(self) -> "ClothingCategory":
        allowed = SUB_CATEGORIES[self.main]
        if self.sub not in allowed:
            raise ValueError(f"'{self.main}'의 중분류가 아님: '{self.sub}' (허용: {allowed})")
        if self.sub == CUSTOM_SUB and not (self.sub_custom and self.sub_custom.strip()):
            raise ValueError(f"sub가 '{CUSTOM_SUB}'이면 sub_custom(직접 입력한 종류)이 필요합니다")
        if self.sub != CUSTOM_SUB and self.sub_custom is not None:
            raise ValueError("sub_custom은 sub='직접입력'일 때만 보낼 수 있습니다")
        return self

    @property
    def resolved_sub(self) -> str:
        """실제 옷 종류 — '직접입력'이면 사용자가 쓴 텍스트. Stage 1 프롬프트는 이 값을 쓴다."""
        return self.sub_custom.strip() if self.sub == CUSTOM_SUB and self.sub_custom else self.sub


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
        """'선택안함' 여부 — True면 Stage 1이 재질 판정을 Vision 추정에 위임한다.

        (analysis.py의 재질 병합 규칙: 사용자 값 우선, '선택안함'일 때만 Vision 값 채택)
        """
        return self.material == MATERIAL_UNKNOWN
