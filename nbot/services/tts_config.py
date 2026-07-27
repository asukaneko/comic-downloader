"""TTS/STT configuration helpers shared by QQ and Web code paths."""
import configparser

from nbot.web.utils.config_loader import get_tts_model_config, get_stt_model_config, resolve_runtime_api_key

config_parser = configparser.ConfigParser()
config_parser.read("config.ini", encoding="utf-8")


def normalize_tts_config(model_config: dict) -> dict:
    """Return normalized TTS settings for a raw model or purpose config."""
    model_config = model_config or {}
    provider_type = model_config.get("provider_type", "openai_compatible")
    api_key = resolve_runtime_api_key(model_config.get("api_key", ""), provider_type)
    voice = (model_config.get("tts_voice") or model_config.get("voice") or "").strip()
    if not voice or voice == "default":
        voice = "alloy"
    return {
        "api_key": api_key,
        "base_url": model_config.get("base_url") or "https://api.openai.com/v1",
        "proxy_url": model_config.get("proxy_url") or "",
        "tts_provider": model_config.get("tts_provider", ""),
        "provider_type": provider_type,
        "tts_url": model_config.get("tts_url") or "",
        "tts_model": (
            model_config.get("tts_model")
            or model_config.get("model")
            or "gpt-4o-mini-tts"
        ),
        "tts_voice": voice,
        "tts_speed": model_config.get("tts_speed") or model_config.get("speed") or 1.0,
        "tts_pitch": model_config.get("tts_pitch") or model_config.get("pitch") or 1.0,
        "tts_volume": model_config.get("tts_volume") or model_config.get("volume") or 1.0,
        "tts_format": model_config.get("tts_format") or "mp3",
        "tts_upload_url": model_config.get("tts_upload_url") or "",
        "tts_headers": model_config.get("tts_headers") or "",
        "tts_body_template": model_config.get("tts_body_template") or "",
        "tts_resource_id": model_config.get("tts_resource_id") or "",
        "tts_ref_audio": model_config.get("tts_ref_audio") or "",
        "tts_user": model_config.get("tts_user") or "",
    }


def get_tts_config_from_server(server, model_id: str = "") -> dict:
    """Resolve TTS config from web server state, honoring the active TTS model."""
    models = getattr(server, "ai_models", []) or []
    requested_model_id = (model_id or "").strip()
    active_model_id = (
        requested_model_id
        or (getattr(server, "active_models_by_purpose", {}) or {}).get("tts")
    )

    if active_model_id:
        for model in models:
            if model.get("id") == active_model_id and model.get("enabled", True):
                return normalize_tts_config(model)

    for model in models:
        if model.get("purpose", "chat") == "tts" and model.get("enabled", True):
            return normalize_tts_config(model)

    return get_tts_config()


def get_tts_config() -> dict:
    """Return normalized TTS settings for adapter calls."""
    tts_config = get_tts_model_config()
    if tts_config and tts_config.get("api_key"):
        return normalize_tts_config(tts_config)
    return {
        "api_key": config_parser.get("ApiKey", "api_key", fallback=""),
        "base_url": "https://api.openai.com/v1",
        "provider_type": "openai_compatible",
        "tts_provider": "openai",
        "tts_url": "",
        "tts_model": "gpt-4o-mini-tts",
        "tts_voice": "alloy",
        "tts_speed": 1.0,
        "tts_pitch": 1.0,
        "tts_volume": 1.0,
        "tts_format": "mp3",
        "tts_upload_url": "",
        "tts_headers": "",
        "tts_body_template": "",
        "tts_resource_id": "",
        "tts_ref_audio": "",
        "tts_user": "",
    }


def normalize_stt_config(model_config: dict) -> dict:
    """Return normalized STT settings for a raw model or purpose config."""
    model_config = model_config or {}
    provider_type = model_config.get("provider_type", "openai_compatible")
    api_key = resolve_runtime_api_key(model_config.get("api_key", ""), provider_type)
    return {
        "api_key": api_key,
        "base_url": model_config.get("base_url") or "",
        "proxy_url": model_config.get("proxy_url") or "",
        "provider_type": provider_type,
        "stt_provider": model_config.get("stt_provider", ""),
        "stt_url": model_config.get("stt_url") or "",
        "stt_model": (
            model_config.get("stt_model")
            or model_config.get("model")
            or "whisper-1"
        ),
        "stt_language": (
            model_config.get("stt_language")
            or model_config.get("language")
            or "zh"
        ),
        "stt_headers": model_config.get("stt_headers") or "",
        "device": model_config.get("device") or "",
        "compute_type": model_config.get("compute_type") or "",
        "beam_size": model_config.get("beam_size") or 5,
    }
