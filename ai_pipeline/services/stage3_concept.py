"""Stage 3 — 컨셉 이미지 생성 (Nano Banana / Gemini 이미지 모델).

Stage 2의 design_spec(image_prompt + base_product)과 옷 사진을 받아,
다중 이미지 융합으로 재창조 컨셉 이미지를 생성한다.

입력 구성 (Interactions API, 이미지 최대 14장):
  [0] image_prompt (영문 편집 지시문 — Stage 2가 생성)
  [1] 옷 사진 (사용자 업로드)
  [2] base_product 레퍼런스 이미지 (data/_index.json에서 product_id로 조회)

주의:
- 모델 ID: gemini-3.1-flash-image (반복 테스트) / gemini-3-pro-image (발표용 최종컷)
- GOOGLE_API_KEY 필요 (.env) — settings.google_api_key로 명시 전달
"""
from __future__ import annotations

import base64
import mimetypes
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

from ai_pipeline.config import settings
from ai_pipeline.schemas.design_spec import DesignSpec
from ai_pipeline.services import brand_assets
from ai_pipeline.services.llm_client import _write_trace

_client = None


def _get_client():
    global _client
    if _client is None:
        from google import genai  # 지연 import — 키 없는 단위 테스트에서 불필요한 의존 방지

        _client = genai.Client(api_key=settings.google_api_key or None)
    return _client


@dataclass
class ConceptImage:
    """후보 1개의 생성 결과."""
    spec: DesignSpec
    image_path: Path
    trace_id: str
    reference_used: str | None  # 사용한 레퍼런스 product_id (없으면 None)


def _encode_image(path: Path) -> dict:
    mime = mimetypes.guess_type(path.name)[0] or "image/png"
    data = base64.b64encode(path.read_bytes()).decode("utf-8")
    return {"type": "image", "data": data, "mime_type": mime}


def build_inputs(spec: DesignSpec, clothing_image_path: Path) -> tuple[list[dict], str | None]:
    """Interactions API의 input 배열 조립. (inputs, 사용한 레퍼런스 id)를 반환.

    base_product가 인덱스에 없으면(모델이 목록 밖 id를 쓴 경우) 레퍼런스 없이 진행 —
    image_prompt가 제품을 서술하고 있으므로 생성은 가능하다. 경고는 호출부에서 로깅.
    """
    prompt = (
        f"{spec.image_prompt}\n\n"
        "The first image is the customer's old clothing (source of patterns/fabric/traces). "
        "The second image, if present, is the MCM base product to be transformed.\n"
        # 로고 충실도 — 'MOM' 뭉개짐 방지. 하네스가 항상 부착 (LLM 재량에 맡기지 않음)
        "Brand lettering fidelity: every MCM logo and monogram lettering must read exactly "
        "as the three letters M-C-M, crisp and undistorted — never 'MOM', 'MCN' or similar "
        "corruption. Alternating upside-down rows are an authentic Visetos pattern feature "
        "and are correct; only the letterforms themselves must stay accurate."
    )
    inputs: list[dict] = [
        {"type": "text", "text": prompt},
        _encode_image(clothing_image_path),
    ]

    # base_product=None: 레퍼런스-프리 모드(악세사리) — 옷 사진 + 프롬프트만으로 생성
    ref = brand_assets.find_by_product_id(spec.base_product) if spec.base_product else None
    if ref is not None:
        inputs.append(_encode_image(settings.asset_root / ref["file"]))
        return inputs, ref["product_id"]
    return inputs, None


def generate_concept_image(
    spec: DesignSpec,
    clothing_image_path: Path,
    *,
    out_dir: Path | None = None,
    use_pro: bool = False,
    trace_id: str | None = None,
) -> ConceptImage:
    """후보 1개 → 컨셉 이미지 1장 생성 후 PNG로 저장."""
    trace_id = trace_id or str(uuid.uuid4())
    model = settings.image_model_pro if use_pro else settings.image_model
    out_dir = out_dir or settings.image_output_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    inputs, reference_used = build_inputs(spec, clothing_image_path)

    t0 = time.monotonic()
    interaction = _get_client().interactions.create(
        model=model,
        input=inputs,
        response_format={
            "type": "image",
            "mime_type": "image/jpeg",      # API 제약: jpeg만 지원 (png 요청 시 400)
            "aspect_ratio": "1:1",          # 정면 제품 컷 — Meshy(Stage 4) 친화 구도
            "image_size": settings.image_size,
        },
    )
    latency_ms = int((time.monotonic() - t0) * 1000)

    out_path = out_dir / f"{trace_id[:8]}_{spec.risk_profile}.jpg"
    out_path.write_bytes(base64.b64decode(interaction.output_image.data))

    _write_trace(
        trace_id=trace_id,
        stage="3",
        model=model,
        latency_ms=latency_ms,
        risk_profile=spec.risk_profile,
        reference_used=reference_used,
        output_ref=str(out_path),
    )
    return ConceptImage(spec=spec, image_path=out_path, trace_id=trace_id, reference_used=reference_used)


def generate_concept_images(
    candidates: list[DesignSpec],
    clothing_image_path: Path,
    *,
    use_pro: bool = False,
) -> list[ConceptImage]:
    """후보 전체(보통 3개) → 컨셉 이미지 n장. 개별 실패는 건너뛰고 성공분만 반환."""
    results: list[ConceptImage] = []
    for spec in candidates:
        try:
            results.append(
                generate_concept_image(spec, clothing_image_path, use_pro=use_pro)
            )
        except Exception as e:  # noqa: BLE001 — 후보 하나 실패가 전체를 죽이면 안 됨
            print(f"⚠️ 후보 '{spec.concept_name}' 생성 실패: {e}")
    if not results:
        raise RuntimeError("모든 후보의 이미지 생성이 실패했습니다")
    return results
