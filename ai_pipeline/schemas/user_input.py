"""Stage 1 입력(user_input) 스키마 — ✅ 프론트엔드 확정본 (2026-08-12 통보 기준).

소유: Stage 1 담당 (팀원). 아래 토글 선택지는 프론트 UI와 1:1로 확정된 계약이다.
값을 바꾸려면 프론트엔드 팀과 재협의 필수.

계약 상대가 analysis.py와 다르다:
- analysis.py  → Stage 1 ↔ Stage 2 (창현) 사이의 계약
- user_input.py → Stage 1 ↔ 프론트엔드/백엔드 사이의 계약

⚠️ 확정 반영 시 변경된 것 (Stage 1 담당자 확인 필요):
- 대분류가 상의/하의/아우터/... → 의류/가방/악세사리 로 재편 (기타 없음 — 자유 입력 분기 제거)
- 재질의 '모르겠어요' → '선택안함' 으로 명칭 변경.
  Stage 1 프롬프트의 재질 병합 규칙("모르겠어요면 Vision 추정 채택") 문구도 맞춰 바꿀 것!

참고: 이 스키마는 사용자 입력 검증용이라 Structured Outputs 제약과 무관하다.
max_length 같은 수치 제약을 자유롭게 써도 된다.
"""
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

# ---------------------------------------------------------------------------
# 토글 선택지 (= 프론트 UI와 1:1, 2026-08-12 확정)
# ---------------------------------------------------------------------------

MainCategory = Literal["의류", "가방", "악세사리"]

SUB_CATEGORIES: dict[str, list[str]] = {
    "의류": ["니트", "가디건", "셔츠", "자켓", "원피스", "후드티", "블라우스", "팬츠"],
    "가방": ["핸드백", "토트백", "백팩", "클러치", "트래블"],
    "악세사리": ["벨트", "스카프", "지갑", "키링", "헤어밴드"],
}

Material = Literal["데님", "가죽", "니트", "울", "면", "린넨", "벨벳", "레이스", "선택안함"]

# 상태 토글은 프론트 확정 통보에 없었음 — 기존 정의 유지 (변경 시 여기도 확정 반영)
Condition = Literal["해짐", "색 바램", "얼룩", "늘어남", "새것 같음"]

STORY_MAX_LENGTH = 500

MATERIAL_UNKNOWN = "선택안함"   # 이 값이면 Stage 1이 재질 판정을 Vision 추정에 위임


# ---------------------------------------------------------------------------
# 스키마
# ---------------------------------------------------------------------------


class ClothingCategory(BaseModel):
    model_config = ConfigDict(extra="forbid")

    main: MainCategory
    sub: str  # SUB_CATEGORIES[main] 중 하나

    @model_validator(mode="after")
    def sub_must_belong_to_main(self) -> "ClothingCategory":
        allowed = SUB_CATEGORIES[self.main]
        if self.sub not in allowed:
            raise ValueError(f"'{self.main}'의 중분류가 아님: '{self.sub}' (허용: {allowed})")
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
        """'선택안함' 여부 — True면 Stage 1이 재질 판정을 Vision 추정에 위임한다.

        (analysis.py의 재질 병합 규칙: 사용자 값 우선, '선택안함'일 때만 Vision 값 채택)
        """
        return self.material == MATERIAL_UNKNOWN
