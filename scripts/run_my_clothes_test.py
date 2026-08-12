import json
import sys
from pathlib import Path

# UTF-8 콘솔 출력 설정
sys.stdout.reconfigure(encoding="utf-8")

# 프로젝트 루트 import 설정
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from ai_pipeline.schemas.analysis import AnalysisResult
from ai_pipeline.schemas.user_input import ClothingCategory, UserInput
from ai_pipeline.services.stage1_narrative import analyze

story_text = (
    "처음 이 원피스를 샀던 날이 아직도 기억난다. 푸른색이 유난히 예뻐서 한참을 고민하다가 결국 거울 앞에서 입어보고 샀던 옷이다. "
    "처음에는 특별한 날에만 입으려고 했지만, 생각보다 마음에 들어서 친구들과 카페에 갈 때도, 가족과 외출할 때도 자주 입었다. "
    "그러다 어느 여름날, 가장 친한 친구와 바닷가에 놀러 가면서 이 원피스를 입었다. 파란 바다와 원피스 색이 잘 어울려서 서로 사진을 "
    "찍어주며 하루 종일 웃었던 기억이 난다. 그날 찍은 사진을 보면 원피스보다 친구와 함께했던 시간이 먼저 떠오른다. "
    "시간이 지나면서 옷은 조금 낡았지만, 이 원피스를 버리지 못하는 이유도 바로 그때의 추억 때문이다. 앞으로도 가끔 꺼내 입으며 "
    "그날의 즐거웠던 순간을 떠올리고 싶다."
)

user_input = UserInput(
    category=ClothingCategory(main="상의", sub="셔츠"),
    material="데님",
    story=story_text,
)

# 실제 이미지 경로 (PNG 포맷)
image_path = Path("data/bag/my_clothes1.png")
if not image_path.exists():
    image_path = Path("data/my_clothes1.png")

print(f"🚀 Claude Sonnet (Stage 1) 실호출 시작...")
print(f"   - 이미지 파일: {image_path} (크기: {image_path.stat().st_size:,} bytes)")
print(f"   - 입력 사연 길이: {len(user_input.story)}자")

result = analyze(image_path=image_path, user_input=user_input)

print("\n✅ [SUCCESS] Claude Sonnet 멀티모달 API 분석 완료!")
print(f"   - AnalysisResult 객체 검증 통과: {isinstance(result, AnalysisResult)}")

# 결과 JSON 저장
out_path = Path("storage/my_clothes1_analysis_result.json")
out_path.parent.mkdir(parents=True, exist_ok=True)
out_path.write_text(json.dumps(result.model_dump(), ensure_ascii=False, indent=2), encoding="utf-8")
print(f"   - 분석 결과 저장 위치: {out_path}")
