"""파이프라인 전역 설정. 경로·모델 ID의 단일 원천."""
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=PROJECT_ROOT / ".env", extra="ignore")

    # API 키 — .env의 ANTHROPIC_API_KEY를 여기로 읽어 llm_client가 명시적으로 전달한다
    # (pydantic-settings는 .env를 os.environ에 넣어주지 않으므로 SDK 자동 감지에 의존하면 안 됨)
    anthropic_api_key: str = ""

    # API 키 — Stage 3 (Gemini 이미지 생성)
    google_api_key: str = ""

    # API 키 — Stage 4 (Meshy image-to-3D)
    meshy_api_key: str = ""
    meshy_base_url: str = "https://api.meshy.ai/openapi/v1"
    meshy_poll_interval_s: float = 5.0    # 폴링 주기
    meshy_timeout_s: float = 600.0        # 생성 대기 상한 (보통 30~60초, 여유 있게)

    # 모델 (AI_Dev_PipeLine.md 3절)
    llm_model: str = "claude-sonnet-5"        # Stage 1·2·5
    gate_model: str = "claude-haiku-4-5"      # 검증 게이트 (effort 파라미터 미지원 주의)
    image_model: str = "gemini-3.1-flash-image"      # Stage 3 (Nano Banana 2 — 반복 테스트용)
    image_model_pro: str = "gemini-3-pro-image"      # Stage 3 발표용 최종컷 (Nano Banana Pro)
    image_size: str = "1K"                    # 512px | 1K | 2K | 4K — 데모/Meshy에는 1K면 충분

    demo_mode: str = "live"                   # live | replay

    # Stage 2
    n_candidates: int = 3                     # 후보 수 (risk_profile 3종과 맞물림)
    n_reference_images: int = 3               # 호출당 주입할 레퍼런스 이미지 수

    # 경로
    asset_index_path: Path = PROJECT_ROOT / "data" / "_index.json"
    asset_root: Path = PROJECT_ROOT / "data"
    brand_assets_path: Path = PROJECT_ROOT / "ai_pipeline" / "data" / "mcm_brand_assets.json"
    log_dir: Path = PROJECT_ROOT / "storage" / "logs"
    image_output_dir: Path = PROJECT_ROOT / "storage" / "images"
    model_output_dir: Path = PROJECT_ROOT / "storage" / "models"

    @field_validator("anthropic_api_key", "google_api_key", "meshy_api_key")
    @classmethod
    def _reject_garbage_keys(cls, v: str) -> str:
        """.env 인라인 주석이 값으로 파싱된 경우 등 — 키처럼 보이지 않으면 빈 값 취급."""
        v = v.strip()
        if "#" in v or " " in v:
            return ""
        return v


settings = Settings()
