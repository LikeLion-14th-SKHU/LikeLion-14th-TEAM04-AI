"""Stage 4 확인용 실행 스크립트 — 컨셉 이미지 1장을 Meshy로 GLB 3D 모델로 변환.

사용법 (프로젝트 루트에서):
    python scripts/run_stage4.py                                  # storage/images의 최신 컨셉 이미지 사용
    python scripts/run_stage4.py --image storage/images/xxx.jpg   # 특정 이미지 지정

전제: .env에 MESHY_API_KEY 필요.
⚠️ 크레딧 소모 (호출당 수 크레딧, 실패 시 환불). 생성 30~60초.
결과 GLB는 https://gltf-viewer.donmccurdy.com 에 드래그하면 바로 확인 가능.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from ai_pipeline.config import settings  # noqa: E402
from ai_pipeline.services.stage4_meshy_3d import generate_3d_model  # noqa: E402


def latest_concept_image() -> Path:
    images = sorted(settings.image_output_dir.glob("*.jpg")) if settings.image_output_dir.exists() else []
    if not images:
        sys.exit("storage/images/ 에 컨셉 이미지가 없습니다 — 먼저 scripts/run_stage3.py 를 실행하세요")
    return images[-1]


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="Stage 4 실호출 확인 (Meshy image-to-3D)")
    parser.add_argument("--image", default=None, help="컨셉 이미지 경로 (생략하면 storage/images 최신)")
    args = parser.parse_args()

    image = Path(args.image) if args.image else latest_concept_image()
    if not image.exists():
        sys.exit(f"이미지가 없습니다: {image}")

    print(f"입력: {image} | 변환 중... (30~60초)")

    result = generate_3d_model(
        image,
        on_progress=lambda p, s: print(f"  {s:12s} {p:3d}%", flush=True),
    )

    print(f"\n✅ GLB 저장: {result.glb_path.relative_to(PROJECT_ROOT)}")
    if result.consumed_credits is not None:
        print(f"   크레딧 사용: {result.consumed_credits}")
    print("   확인: https://gltf-viewer.donmccurdy.com 에 GLB 드래그")


if __name__ == "__main__":
    main()
