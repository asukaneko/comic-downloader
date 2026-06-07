"""本地 faster-whisper STT 适配器"""
import logging
import os
import threading

from nbot.services.stt_adapters.base import STTAdapter

_log = logging.getLogger(__name__)

# 模型别名映射：云端模型名 -> 本地 whisper 模型名
_MODEL_ALIASES = {
    "whisper-1": "tiny",
    "gpt-4o-mini-transcribe": "base",
    "gpt-4o-transcribe": "base",
}

# 全局模型单例
_model = None
_model_name = None
_model_lock = threading.Lock()


def _get_local_model_dir(model_name: str) -> str:
    """Return the project-local model directory for a whisper model."""
    model_root = os.path.abspath(os.path.join("data", "models", "faster-whisper"))
    safe_name = str(model_name).replace("/", "--").replace("\\", "--").strip()
    return os.path.join(model_root, safe_name)


class LocalWhisperSTTAdapter(STTAdapter):
    """本地 faster-whisper STT 适配器

    使用本地 faster-whisper 模型进行语音识别，无需网络请求。
    """

    def get_supported_params(self) -> list:
        return ["model", "language", "device", "compute_type", "beam_size"]

    def transcribe(self, audio_file_path: str, config: dict, language: str = None) -> str:
        model, stt_config = self._ensure_model_loaded(config)
        lang = language or stt_config.get("language") or "zh"
        beam_size = stt_config.get("beam_size", 5)

        _log.info(
            "Local Whisper STT: model=%s, lang=%s, beam_size=%d",
            stt_config.get("model_name", "unknown"), lang, beam_size,
        )
        segments, info = model.transcribe(
            audio_file_path,
            beam_size=beam_size,
            language=lang,
        )
        text = "".join(segment.text for segment in segments).strip()
        return text

    @staticmethod
    def _ensure_model_loaded(config: dict):
        """Load the faster-whisper model once and reuse it for later requests."""
        global _model, _model_name

        model_name = (
            config.get("stt_model")
            or config.get("model")
            or os.environ.get("NBOT_FASTER_WHISPER_MODEL")
            or "tiny"
        )
        model_name = _MODEL_ALIASES.get(str(model_name).strip(), model_name)

        if _model is not None and _model_name == model_name:
            return _model, {
                "model_name": model_name,
                "language": config.get("stt_language") or config.get("language") or "zh",
                "beam_size": config.get("beam_size", 5),
            }

        with _model_lock:
            if _model is not None and _model_name == model_name:
                return _model, {
                    "model_name": model_name,
                    "language": config.get("stt_language") or config.get("language") or "zh",
                    "beam_size": config.get("beam_size", 5),
                }

            try:
                from faster_whisper import WhisperModel
            except ImportError as exc:
                raise RuntimeError(
                    "faster-whisper is not installed. Run `pip install faster-whisper`."
                ) from exc

            device = config.get("device") or os.environ.get("NBOT_FASTER_WHISPER_DEVICE") or "cpu"
            compute_type = (
                config.get("compute_type")
                or os.environ.get("NBOT_FASTER_WHISPER_COMPUTE_TYPE")
                or "int8"
            )

            model_path = _get_local_model_dir(model_name)
            model_source = model_path if os.path.isdir(model_path) else model_name

            _log.info(
                "Loading faster-whisper model '%s' from %s on %s (%s)",
                model_name,
                model_source,
                device,
                compute_type,
            )
            _model = WhisperModel(
                model_source,
                device=device,
                compute_type=compute_type,
            )
            _model_name = model_name

            beam_size_raw = config.get("beam_size") or os.environ.get("NBOT_FASTER_WHISPER_BEAM_SIZE") or 5
            try:
                beam_size = max(1, int(beam_size_raw))
            except (TypeError, ValueError):
                beam_size = 5

            return _model, {
                "model_name": model_name,
                "language": config.get("stt_language") or config.get("language") or "zh",
                "beam_size": beam_size,
            }
