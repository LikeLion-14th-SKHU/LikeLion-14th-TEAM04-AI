"""실사진 E2E — 백엔드가 호출할 API 경로 그대로 전체 파이프라인 검증.

흐름: POST /ai/v1/pipeline-run → (stage 1→2→3→게이트) → awaiting_selection
      → POST /ai/v1/jobs/{id}/select → (stage 4→5) → done

사용법 (프로젝트 루트에서):
    python scripts/run_e2e.py                          # 기본: 바람막이 샘플
    python scripts/run_e2e.py --image storage/uploads/e2e_tshirt.jpg --sub 셔츠

⚠️ 실비용: Claude(1·2·5·게이트) + Gemini(3장) + Meshy(~30크레딧, select 후 1회).
"""
from __future__ import annotations

import argparse
import base64
import json
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from fastapi.testclient import TestClient  # noqa: E402

from ai_pipeline.main import app  # noqa: E402

# 테스트용 사연 (실제 서비스에서는 사용자 입력)
DEFAULT_STORY = (
    "고등학교 3년 내내 입었던 바람막이다. 야간자율학습이 끝나면 밤 11시, "
    "이걸 걸치고 자전거로 강변길을 달려 집에 갔다. 바람이 옷을 두드리는 소리가 "
    "그날 하루의 마침표 같았다. 수능 전날 밤에도, 합격 발표를 보러 가던 아침에도 "
    "이 옷을 입고 있었다. 소매 끝이 다 해졌지만 버릴 수가 없다. "
    "내 10대의 밤공기가 전부 이 옷에 배어 있는 것 같아서."
)


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="실사진 E2E (pipeline-run → select → done)")
    parser.add_argument("--image", default="storage/uploads/e2e_jacket.jpg")
    parser.add_argument("--sub", default="자켓", help="서브카테고리 (기본: 자켓)")
    parser.add_argument("--material", default="선택안함")
    parser.add_argument("--story", default=DEFAULT_STORY)
    parser.add_argument("--select", type=int, default=0, help="선택할 후보 인덱스 (기본: 게이트 최고점)")
    args = parser.parse_args()

    image = Path(args.image)
    if not image.exists():
        sys.exit(f"이미지가 없습니다: {image}")

    client = TestClient(app)
    b64 = base64.b64encode(image.read_bytes()).decode()
    t0 = time.monotonic()

    print(f"[1/4] POST /ai/v1/pipeline-run — {image.name}, 의류/{args.sub}, {args.material}", flush=True)
    r = client.post("/ai/v1/pipeline-run", json={
        "image_base64": b64,
        "user_input": {
            "category": {"main": "의류", "sub": args.sub},
            "material": args.material,
            "story": args.story,
        },
    })
    r.raise_for_status()
    job_id = r.json()["job_id"]
    print(f"      job_id={job_id} (TestClient는 백그라운드 태스크를 동기 실행 — stage 1~3+게이트 완료됨)", flush=True)

    print("[2/4] GET /ai/v1/jobs/{job_id} — 후보 확인", flush=True)
    info = client.get(f"/ai/v1/jobs/{job_id}").json()
    if info["status"] != "awaiting_selection":
        sys.exit(f"❌ 예상 밖 상태: {info['status']} — error: {info.get('error')} / detail: {info.get('detail')}")
    result = info["result"]
    print(f"      all_failed={result['all_failed']} regenerated={result['regenerated']}", flush=True)
    for c in result["candidates"]:
        s, g = c["spec"], c["gate"]
        print(f"      [{c['index']}] {s['risk_profile']:8s} Lv{s['intervention_level']} "
              f"{s['concept_name']} → {s['base_product']} | 게이트 {'통과' if g['passed'] else '탈락'} {g['score']}점", flush=True)
        print(f"           이미지: {c['image_url']}", flush=True)

    print(f"[3/4] POST /ai/v1/jobs/{job_id}/select — 후보 {args.select}번 선택 → 3D 변환 (수 분)", flush=True)
    r = client.post(f"/ai/v1/jobs/{job_id}/select", json={"candidate_index": args.select})
    r.raise_for_status()

    print("[4/4] 최종 결과", flush=True)
    info = client.get(f"/ai/v1/jobs/{job_id}").json()
    if info["status"] != "done":
        sys.exit(f"❌ 예상 밖 상태: {info['status']} — error: {info.get('error')} / detail: {info.get('detail')}")
    result = info["result"]
    print(f"      GLB:      {result['glb_url']}", flush=True)
    print(f"      정면 PNG: {result['front_image_url']}", flush=True)
    for rec in result["curation"]["recommendations"]:
        print(f"      추천: {rec['name_kr']} ({rec['product_id']}) — {rec['tagline']}", flush=True)

    out = PROJECT_ROOT / "storage" / f"e2e_{image.stem}_result.json"
    out.write_text(json.dumps(info, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n✅ E2E 완료 ({time.monotonic() - t0:.0f}초) — 전체 결과: {out.relative_to(PROJECT_ROOT)}", flush=True)


if __name__ == "__main__":
    main()
