"""이미 생성된 GLB에서 정면 투명배경 PNG(front_image)를 소급 렌더한다.

pyrender/OSMesa 설정이 안 돼있던 시기에 만들어진 GLB들은 front_image가 비어있다.
Meshy를 다시 호출할 필요 없이(크레딧 소모 없음), storage/models/에 이미 있는 GLB
파일들만 다시 렌더해서 채운다.

사용법:
    python scripts/backfill_front_images.py            # 실제로 렌더 + 저장
    python scripts/backfill_front_images.py --dry-run  # 대상 개수만 확인, 렌더 안 함
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from ai_pipeline.config import settings  # noqa: E402
from ai_pipeline.services.glb_render import render_front_png_safe  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="렌더 안 하고 대상 목록만 출력")
    args = parser.parse_args()

    models_dir = settings.model_output_dir
    glb_files = sorted(models_dir.glob("*.glb"))

    targets = [g for g in glb_files if not g.with_name(f"{g.stem}_front.png").exists()]
    already_done = len(glb_files) - len(targets)

    print(f"전체 GLB: {len(glb_files)}개 / 이미 front.png 있음: {already_done}개 / 대상: {len(targets)}개")

    if args.dry_run:
        for g in targets:
            print(f"  - {g.name}")
        return

    ok, failed = 0, []
    for i, glb_path in enumerate(targets, 1):
        result = render_front_png_safe(glb_path)
        if result:
            ok += 1
            print(f"[{i}/{len(targets)}] OK  {glb_path.name} -> {result.name}")
        else:
            failed.append(glb_path.name)
            print(f"[{i}/{len(targets)}] FAIL {glb_path.name}")

    print(f"\n완료: 성공 {ok}개 / 실패 {len(failed)}개")
    if failed:
        print("실패 목록:", ", ".join(failed))


if __name__ == "__main__":
    main()
