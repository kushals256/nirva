from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    nvidia_api_key: str = ""
    nvidia_base_url: str = "https://integrate.api.nvidia.com/v1"
    nvidia_llm_model: str = "meta/llama-3.1-8b-instruct"
    nvidia_embed_model: str = "nvidia/nv-embedqa-e5-v5"

    deepgram_api_key: str = ""
    deepgram_model: str = "nova-3"
    deepgram_language: str = "multi"

    tts_voice: str = "en-IN-NeerjaNeural"
    tts_voice_hindi: str = "hi-IN-SwaraNeural"

    host: str = "0.0.0.0"
    port: int = 8000
    cors_origins: str = "http://localhost:8000,http://127.0.0.1:8000"

    data_dir: Path = PROJECT_ROOT / "data"
    workspace_dir: Path = PROJECT_ROOT / "workspace"
    chroma_dir: Path = PROJECT_ROOT / "data" / "chroma"

    run_command_timeout: int = 30
    allowed_commands: str = "python,pytest,python3"

    chunk_size: int = 800
    chunk_overlap: int = 120
    rag_top_k: int = 4

    @property
    def allowed_command_list(self) -> list[str]:
        return [c.strip() for c in self.allowed_commands.split(",") if c.strip()]

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


settings = Settings()
