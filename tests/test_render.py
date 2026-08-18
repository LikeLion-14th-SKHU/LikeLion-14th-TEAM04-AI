"""GLB → 정면 투명 PNG 렌더 검증 — 합성 GLB(색칠한 박스)로 실렌더 수행.

pyrender 미설치 환경(팀원 노트북 등)에서는 전체 skip — 파이프라인 필수 요소가 아님.
"""
import numpy as np
import pytest

pyrender = pytest.importorskip("pyrender", reason="pyrender 미설치 (pip install pyrender --no-deps)")
import trimesh  # noqa: E402
from PIL import Image  # noqa: E402

from ai_pipeline.services.glb_render import render_front_png, render_front_png_safe  # noqa: E402


@pytest.fixture
def synthetic_glb(tmp_path):
    """비대칭 합성 GLB — 박스(주황) + 앞면에 원기둥(파랑) 돌출.

    앞뒤가 다른 형태라 정면 렌더 여부를 픽셀로 검증할 수 있다.
    """
    box = trimesh.creation.box(extents=(2.0, 1.2, 0.6))
    box.visual = trimesh.visual.ColorVisuals(box, vertex_colors=[220, 120, 40, 255])

    knob = trimesh.creation.cylinder(radius=0.25, height=0.5)
    knob.apply_translation([0, 0, 0.55])          # +Z(정면) 쪽으로 돌출
    knob.visual = trimesh.visual.ColorVisuals(knob, vertex_colors=[40, 80, 220, 255])

    scene = trimesh.Scene([box, knob])
    path = tmp_path / "synthetic.glb"
    scene.export(path)
    return path


def test_render_front_png_transparent_background(synthetic_glb, tmp_path):
    out = render_front_png(synthetic_glb, tmp_path / "front.png", size=256)

    img = np.array(Image.open(out))
    assert img.shape == (256, 256, 4), "RGBA여야 함"

    # 네 모서리는 완전 투명 (배경)
    for corner in (img[0, 0], img[0, -1], img[-1, 0], img[-1, -1]):
        assert corner[3] == 0, f"모서리가 투명하지 않음: alpha={corner[3]}"

    # 중앙은 불투명 (제품)
    assert img[128, 128, 3] == 255, "중앙에 제품이 렌더되지 않음"

    # 제품이 프레임의 유의미한 면적을 차지 (자동 프레이밍 동작 확인)
    opaque_ratio = (img[:, :, 3] > 0).mean()
    assert 0.15 < opaque_ratio < 0.95, f"프레이밍 이상: 불투명 비율 {opaque_ratio:.2f}"


def test_render_front_default_output_path(synthetic_glb):
    out = render_front_png(synthetic_glb, size=128)
    assert out == synthetic_glb.with_name("synthetic_front.png")
    assert out.exists()


def test_y_rotation_changes_view(synthetic_glb, tmp_path):
    """180° 돌리면 정면 돌출(파랑 원기둥)이 안 보여야 함 — 보정 노브 동작 검증."""
    front = np.array(Image.open(render_front_png(synthetic_glb, tmp_path / "f.png", size=256)))
    back = np.array(Image.open(render_front_png(synthetic_glb, tmp_path / "b.png", size=256, y_rotation_deg=180)))

    def blue_pixels(img) -> int:
        opaque = img[:, :, 3] > 0
        blue = (img[:, :, 2].astype(int) - img[:, :, 0].astype(int)) > 60
        return int((opaque & blue).sum())

    assert blue_pixels(front) > 100, "정면에서 파랑 돌출부가 보여야 함"
    assert blue_pixels(back) < blue_pixels(front) / 5, "180° 회전 시 돌출부가 가려져야 함"


def test_safe_wrapper_returns_none_on_garbage(tmp_path):
    bad = tmp_path / "broken.glb"
    bad.write_bytes(b"not a glb at all")
    assert render_front_png_safe(bad) is None
