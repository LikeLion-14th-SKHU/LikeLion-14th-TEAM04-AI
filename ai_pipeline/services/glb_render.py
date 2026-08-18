"""GLB → 정면 2D 썸네일 렌더 (투명 배경 PNG).

용도: 컬렉션 그리드에서 GLB 뷰어 여러 개를 띄우면 무거우므로,
Stage 4 완료 시점에 서버가 정면 1컷을 투명 배경으로 미리 렌더해 둔다.
- 그리드: front PNG를 <img>로 (가볍고 배경 자유)
- 상세: glb_url을 <model-viewer>로 (인터랙티브)

의존성 설치 주의 (pyrender가 구버전 PyOpenGL을 고정해 빌드가 깨짐):
    pip install -r requirements.txt          # trimesh, PyOpenGL>=3.1.7 등
    pip install pyrender --no-deps           # 의존성 무시 설치 (별도 1회)
pyrender가 없으면 렌더는 조용히 건너뛴다 (front_image_url=null) — 파이프라인은 계속 동작.

한계: pyrender의 PBR 표현은 브라우저 뷰어보다 단순 — 썸네일 용도 품질.
Meshy 산출물의 '정면'이 +Z가 아닐 경우 y_rotation_deg로 보정한다 (실 GLB 확인 후 튜닝).
"""
from __future__ import annotations

import math
from pathlib import Path

import numpy as np


def render_front_png(
    glb_path: Path,
    out_path: Path | None = None,
    *,
    size: int = 1024,
    y_rotation_deg: float = 0.0,   # 정면 방향 보정 노브 (Meshy 실물 확인 후 조정)
    margin: float = 1.35,          # 프레이밍 여백 (1.0 = 꽉 참)
) -> Path:
    """GLB를 정면에서 렌더해 투명 배경 PNG로 저장하고 경로를 반환한다."""
    import pyrender  # 지연 import — 미설치 환경에서 모듈 로드는 가능하게
    import trimesh
    from PIL import Image

    out_path = out_path or glb_path.with_name(f"{glb_path.stem}_front.png")

    # --- 로드 & 정면 보정 회전 ---
    tm = trimesh.load(glb_path, force="scene")
    if y_rotation_deg:
        rot = trimesh.transformations.rotation_matrix(
            math.radians(y_rotation_deg), [0, 1, 0], point=tm.bounds.mean(axis=0)
        )
        tm.apply_transform(rot)

    # --- pyrender 씬 구성 (배경 완전 투명) ---
    # ⚠️ tm.geometry.values()는 씬 그래프 변환(회전·노드 배치)이 미적용된 원본이므로
    #    dump()로 변환을 베이크한 사본을 사용해야 한다 (GLB 노드 변환 + y_rotation 반영)
    scene = pyrender.Scene(bg_color=[0.0, 0.0, 0.0, 0.0], ambient_light=[0.35] * 3)
    for geom in tm.dump(concatenate=False):
        scene.add(pyrender.Mesh.from_trimesh(geom, smooth=False))

    # --- 바운딩 박스 기반 자동 프레이밍 (+Z에서 바라봄) ---
    bounds = tm.bounds                       # (2, 3) [min, max]
    center = bounds.mean(axis=0)
    extent = float(np.max(bounds[1] - bounds[0]))
    yfov = math.pi / 5                       # 36° — 원근 왜곡 적은 제품컷 화각
    distance = (extent / 2) / math.tan(yfov / 2) * margin

    cam_pose = np.eye(4)
    cam_pose[:3, 3] = center + np.array([0.0, 0.0, distance])
    scene.add(pyrender.PerspectiveCamera(yfov=yfov), pose=cam_pose)

    # --- 조명: 정면 키 라이트 + 좌상단 필 라이트 ---
    scene.add(pyrender.DirectionalLight(intensity=3.0), pose=cam_pose)
    fill_pose = np.eye(4)
    fill_pose[:3, :3] = trimesh.transformations.euler_matrix(-0.5, -0.6, 0)[:3, :3]
    scene.add(pyrender.DirectionalLight(intensity=1.2), pose=fill_pose)

    # --- 렌더 & 저장 ---
    renderer = pyrender.OffscreenRenderer(size, size)
    try:
        color, _ = renderer.render(scene, flags=pyrender.RenderFlags.RGBA)
    finally:
        renderer.delete()

    out_path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(color, "RGBA").save(out_path)
    return out_path


def render_front_png_safe(glb_path: Path, **kwargs) -> Path | None:
    """렌더 실패/미설치가 파이프라인을 죽이지 않게 하는 래퍼 — 실패 시 None."""
    try:
        return render_front_png(glb_path, **kwargs)
    except Exception as e:  # noqa: BLE001 — 썸네일은 부가 산출물
        print(f"⚠️ 정면 썸네일 렌더 건너뜀 ({type(e).__name__}: {e}) — glb_url만 제공됩니다")
        return None
