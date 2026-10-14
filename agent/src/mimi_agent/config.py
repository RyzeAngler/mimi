"""Environment-backed configuration for the Mimi Agent."""

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


class ConfigurationError(RuntimeError):
    """Raised when a runtime configuration cannot support the requested feature."""


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    return default if value in (None, "") else int(value)


def _env_float(name: str, default: float) -> float:
    value = os.getenv(name)
    return default if value in (None, "") else float(value)


@dataclass(frozen=True)
class Settings:
    host: str = "0.0.0.0"
    port: int = 8765
    log_level: str = "INFO"

    ark_api_key: str = ""
    ark_model: str = ""
    ark_base_url: str = "https://ark.cn-beijing.volces.com/api/v3"
    ark_timeout_seconds: float = 8.0
    ark_temperature: float = 0.7
    ark_max_tokens: int = 24
    ark_context_turns: int = 10
    ark_service_tier: str = ""

    volcengine_api_key: str = ""
    volcengine_resource_id: str = ""
    volcengine_voice_type: str = ""
    volcengine_tts_bidirectional_url: str = (
        "wss://openspeech.bytedance.com/api/v3/tts/bidirection"
    )
    volcengine_tts_model: str = ""
    volcengine_tts_timeout_seconds: float = 30.0
    first_audio_timeout_seconds: float = 8.0

    audio_sample_rate: int = 16000
    audio_channels: int = 1
    audio_sample_width: int = 2
    log_dir: Path = Path("logs")
    log_max_bytes: int = 10 * 1024 * 1024
    log_backup_count: int = 5

    default_speech_cooldown_ms: int = 2500
    dizzy_speech_cooldown_ms: int = 5000

    runtime_mode: str = "legacy"
    webui_host: str = "127.0.0.1"
    webui_port: int = 8090
    vlm_provider: str = "ollama"
    vlm_base_url: str = "http://127.0.0.1:11434/v1"
    vlm_model: str = ""
    vlm_max_tokens: int = 256
    vlm_request_timeout_seconds: float = 30.0
    vlm_video_window_seconds: float = 1.0
    camera_capture_timeout_seconds: float = 2.0
    camera_jpeg_quality: float = 0.75
    camera_max_edge: int = 320
    camera_frame_rate: float = 4.0

    @classmethod
    def from_env(cls) -> "Settings":
        load_dotenv()
        return cls(
            host=os.getenv("MIMI_AGENT_HOST", cls.host),
            port=_env_int("MIMI_AGENT_PORT", cls.port),
            log_level=os.getenv("MIMI_LOG_LEVEL", cls.log_level),
            ark_api_key=os.getenv("ARK_API_KEY", ""),
            ark_model=os.getenv("ARK_MODEL", cls.ark_model),
            ark_base_url=os.getenv("ARK_BASE_URL", cls.ark_base_url).rstrip("/"),
            ark_timeout_seconds=_env_float(
                "ARK_TIMEOUT_SECONDS", cls.ark_timeout_seconds
            ),
            ark_temperature=_env_float("ARK_TEMPERATURE", cls.ark_temperature),
            ark_max_tokens=_env_int("ARK_MAX_TOKENS", cls.ark_max_tokens),
            ark_context_turns=_env_int("ARK_CONTEXT_TURNS", cls.ark_context_turns),
            ark_service_tier=os.getenv("ARK_SERVICE_TIER", cls.ark_service_tier),
            volcengine_api_key=os.getenv("VOLCENGINE_API_KEY", ""),
            volcengine_resource_id=os.getenv("VOLCENGINE_RESOURCE_ID", ""),
            volcengine_voice_type=os.getenv("VOLCENGINE_VOICE_TYPE", ""),
            volcengine_tts_bidirectional_url=os.getenv(
                "VOLCENGINE_TTS_BIDIRECTIONAL_URL",
                cls.volcengine_tts_bidirectional_url,
            ),
            volcengine_tts_model=os.getenv("VOLCENGINE_TTS_MODEL", ""),
            volcengine_tts_timeout_seconds=_env_float(
                "VOLCENGINE_TTS_TIMEOUT_SECONDS", cls.volcengine_tts_timeout_seconds
            ),
            first_audio_timeout_seconds=_env_float(
                "MIMI_SPEECH_FIRST_AUDIO_TIMEOUT_SECONDS",
                cls.first_audio_timeout_seconds,
            ),
            audio_sample_rate=_env_int("MIMI_AUDIO_SAMPLE_RATE", cls.audio_sample_rate),
            audio_channels=_env_int("MIMI_AUDIO_CHANNELS", cls.audio_channels),
            audio_sample_width=_env_int(
                "MIMI_AUDIO_SAMPLE_WIDTH", cls.audio_sample_width
            ),
            log_dir=Path(os.getenv("MIMI_LOG_DIR", str(cls.log_dir))),
            log_max_bytes=_env_int("MIMI_LOG_MAX_BYTES", cls.log_max_bytes),
            log_backup_count=_env_int("MIMI_LOG_BACKUP_COUNT", cls.log_backup_count),
            default_speech_cooldown_ms=_env_int(
                "MIMI_SPEECH_DEFAULT_COOLDOWN_MS", cls.default_speech_cooldown_ms
            ),
            dizzy_speech_cooldown_ms=_env_int(
                "MIMI_SPEECH_DIZZY_COOLDOWN_MS", cls.dizzy_speech_cooldown_ms
            ),
            runtime_mode=os.getenv("MIMI_RUNTIME_MODE", cls.runtime_mode).lower(),
            webui_host=os.getenv("MIMI_WEBUI_HOST", cls.webui_host),
            webui_port=_env_int("MIMI_WEBUI_PORT", cls.webui_port),
            vlm_provider=os.getenv("MIMI_VLM_PROVIDER", cls.vlm_provider).lower(),
            vlm_base_url=os.getenv("MIMI_VLM_BASE_URL", cls.vlm_base_url).rstrip("/"),
            vlm_model=os.getenv("MIMI_VLM_MODEL", cls.vlm_model),
            vlm_max_tokens=_env_int("MIMI_VLM_MAX_TOKENS", cls.vlm_max_tokens),
            vlm_request_timeout_seconds=_env_float(
                "MIMI_VLM_REQUEST_TIMEOUT_SECONDS", cls.vlm_request_timeout_seconds
            ),
            vlm_video_window_seconds=_env_float(
                "MIMI_VLM_VIDEO_WINDOW_SECONDS", cls.vlm_video_window_seconds
            ),
            camera_capture_timeout_seconds=_env_float(
                "MIMI_CAMERA_CAPTURE_TIMEOUT_SECONDS",
                cls.camera_capture_timeout_seconds,
            ),
            camera_jpeg_quality=_env_float(
                "MIMI_CAMERA_JPEG_QUALITY", cls.camera_jpeg_quality
            ),
            camera_max_edge=_env_int("MIMI_CAMERA_MAX_EDGE", cls.camera_max_edge),
            camera_frame_rate=_env_float(
                "MIMI_CAMERA_FRAME_RATE", cls.camera_frame_rate
            ),
        )

    def validate_runtime_mode(self) -> None:
        if self.runtime_mode not in {"legacy", "vlm"}:
            raise ConfigurationError(
                "MIMI_RUNTIME_MODE must be either legacy or vlm"
            )

    def validate_tts(self) -> None:
        if not self.volcengine_api_key:
            raise ConfigurationError("Configure VOLCENGINE_API_KEY before starting TTS.")
        missing = []
        if not self.volcengine_resource_id:
            missing.append("VOLCENGINE_RESOURCE_ID")
        if not self.volcengine_voice_type:
            missing.append("VOLCENGINE_VOICE_TYPE")
        if missing:
            raise ConfigurationError("Missing TTS configuration: " + ", ".join(missing))

        if not self.volcengine_tts_bidirectional_url.startswith(("ws://", "wss://")):
            raise ConfigurationError(
                "VOLCENGINE_TTS_BIDIRECTIONAL_URL must be a ws:// or wss:// URL"
            )
        if self.audio_sample_rate not in {8000, 16000, 22050, 24000, 32000, 44100, 48000}:
            raise ConfigurationError("MIMI_AUDIO_SAMPLE_RATE is unsupported by TTS")

    def validate_llm(self) -> None:
        missing = []
        if not self.ark_api_key:
            missing.append("ARK_API_KEY")
        if not self.ark_model:
            missing.append("ARK_MODEL")
        if missing:
            raise ConfigurationError("Missing LLM configuration: " + ", ".join(missing))
        if self.first_audio_timeout_seconds <= 0:
            raise ConfigurationError(
                "MIMI_SPEECH_FIRST_AUDIO_TIMEOUT_SECONDS must be positive"
            )
        if self.ark_max_tokens <= 0:
            raise ConfigurationError("ARK_MAX_TOKENS must be positive")
        if self.ark_context_turns <= 0:
            raise ConfigurationError("ARK_CONTEXT_TURNS must be positive")

    def validate_vlm(self) -> None:
        if self.vlm_provider not in {"ollama", "llama-server"}:
            raise ConfigurationError(
                "MIMI_VLM_PROVIDER must be either ollama or llama-server"
            )
        if not self.vlm_model:
            raise ConfigurationError("Missing VLM configuration: MIMI_VLM_MODEL")
        if not self.vlm_base_url.startswith(("http://", "https://")):
            raise ConfigurationError(
                "MIMI_VLM_BASE_URL must be an http:// or https:// URL"
            )
        if self.webui_port <= 0 or self.webui_port > 65535:
            raise ConfigurationError("MIMI_WEBUI_PORT must be between 1 and 65535")
        if self.vlm_max_tokens <= 0:
            raise ConfigurationError("MIMI_VLM_MAX_TOKENS must be positive")
        if self.vlm_request_timeout_seconds <= 0:
            raise ConfigurationError("MIMI_VLM_REQUEST_TIMEOUT_SECONDS must be positive")
        if self.vlm_video_window_seconds <= 0:
            raise ConfigurationError("MIMI_VLM_VIDEO_WINDOW_SECONDS must be positive")
        if self.camera_capture_timeout_seconds <= 0:
            raise ConfigurationError(
                "MIMI_CAMERA_CAPTURE_TIMEOUT_SECONDS must be positive"
            )
        if not 0.1 <= self.camera_jpeg_quality <= 1.0:
            raise ConfigurationError("MIMI_CAMERA_JPEG_QUALITY must be between 0.1 and 1")
        if self.camera_max_edge <= 0:
            raise ConfigurationError("MIMI_CAMERA_MAX_EDGE must be positive")
        if not 1.0 <= self.camera_frame_rate <= 60.0:
            raise ConfigurationError(
                "MIMI_CAMERA_FRAME_RATE must be between 1 and 60"
            )
