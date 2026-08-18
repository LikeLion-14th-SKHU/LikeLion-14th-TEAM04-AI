import json
import sys
from pathlib import Path

# UTF-8 콘솔 출력 설정
sys.stdout.reconfigure(encoding="utf-8")

# 프로젝트 루트 import 설정
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from ai_pipeline.config import settings
from ai_pipeline.schemas.analysis import AnalysisResult
from ai_pipeline.schemas.user_input import ClothingCategory, UserInput
from ai_pipeline.services.stage1_narrative import analyze

story_text = (
    "이 청바지를 보면 오래 입어서 자연스럽게 색이 빠진 청바지가 떠오른다. 처음 샀을 때는 새 옷이라 "
    "아끼면서 입었지만 시간이 지나면서 점점 편해졌다. 학교에 갈 때도 입고 친구를 만나러 갈 때도 자주 "
    "입다 보니 어느 순간 가장 손이 많이 가는 바지가 되었다. 특히 시험이 끝난 날 친구들과 아무 계획 없이 "
    "돌아다녔던 날들이 기억에 남는다. 카페에 갓다가 날씨가 좋아서 한참 걸어다니기도 하고, 늦은 시간까지 "
    "이야기를 하면서 집에 돌아오기도 했다. 특별한 일이 있었던 날은 아니지만 지금 생각하면 그런 평범한 "
    "하루들이 오히려 오래 기억에 남는 것 같다. 무릅과 주머니 주변의 색이 조금씩 달라진 것도 그동안 많이 "
    "입었다는 흔적이다. 새 청바지를 사면 이 바지를 정리할까 생각도 했지만 아직은 버리기 아깝다. 앞으로도 "
    "편하게 입으면서 조금 더 오래 입어볼 생각이다. 별거 아닌 옷이지만 지나간 시간들이 묻어있어서 그런지 "
    "쉽게 버릴수가 없다."
)

user_input = UserInput(
    category=ClothingCategory(main="하의", sub="트레이닝팬츠"),
    material="데님",
    condition=["색 바램", "해짐"],
    story=story_text,
)

image_path = Path("data/bag/my_clothes2.png")

print(f"🚀 Claude Sonnet (Stage 1) 실제 API 호출 준비...")
print(f"   - 이미지 파일: {image_path} (크기: {image_path.stat().st_size:,} bytes)")
print(f"   - 사용 모델: {settings.llm_model}")
print(f"   - 입력 사연 길이: {len(user_input.story)}자")

try:
    result = analyze(image_path=image_path, user_input=user_input)
    print("\n✅ [SUCCESS] Claude 멀티모달 API 호출 성공!")
    
    # Validation 검증
    is_valid = isinstance(result, AnalysisResult)
    print(f"   - AnalysisResult Pydantic 검증: {is_valid}")
    
    out_path = Path("storage/my_clothes2_analysis_result.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result.model_dump(), ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"   - 결과 JSON 저장: {out_path}")

except Exception as e:
    print(f"\n❌ [ERROR] API 호출 또는 처리 중 오류 발생: {e}")
    sys.exit(1)
