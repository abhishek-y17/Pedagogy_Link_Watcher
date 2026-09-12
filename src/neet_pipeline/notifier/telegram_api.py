"""
Thin wrapper around the Telegram Bot API. No secrets in code: the token and
chat id are read from config/.env (see config/.env.example) at call time,
never hardcoded, and every lookup fails LOUDLY (raises) if missing rather
than silently doing nothing.

Send-only: sendMessage + sendDocument. The Verify/Reject button flow and its
long-polling bot were removed (the scheduled model has no always-on process
to receive updates), so answerCallbackQuery / editMessageReplyMarkup /
getUpdates and inline-keyboard reply_markup are gone with them.
"""

from __future__ import annotations
import os
import requests
from dotenv import dotenv_values

DEFAULT_ENV_PATH = os.path.join("config", ".env")
API_BASE = "https://api.telegram.org/bot{token}/{method}"


class TelegramConfigError(RuntimeError):
    pass


def _load_env(env_path: str = DEFAULT_ENV_PATH) -> dict:
    # real process env vars win over the file, so a hosted deployment can
    # set them in the platform dashboard (see docs/HOSTING.md) without a file
    return {**dotenv_values(env_path), **os.environ}


def _get_required_env(name: str, env_path: str = DEFAULT_ENV_PATH) -> str:
    value = _load_env(env_path).get(name)
    if not value:
        raise TelegramConfigError(
            f"{name} is not set (checked {env_path} and process env). "
            f"Put it in config/.env (see config/.env.example) -- never hardcode it."
        )
    return value


def get_bot_token(env_path: str = DEFAULT_ENV_PATH, env_var: str = "TELEGRAM_BOT_TOKEN") -> str:
    return _get_required_env(env_var, env_path)


def get_chat_id(env_path: str = DEFAULT_ENV_PATH, env_var: str = "TELEGRAM_CHAT_ID") -> str:
    return _get_required_env(env_var, env_path)


def get_credentials(env_path: str = DEFAULT_ENV_PATH,
                    token_var: str = "TELEGRAM_BOT_TOKEN",
                    chat_id_var: str = "TELEGRAM_CHAT_ID") -> tuple[str, str]:
    return get_bot_token(env_path, token_var), get_chat_id(env_path, chat_id_var)


DEFAULT_TIMEOUT = 30
# Real KEA result PDFs run into the multi-MB range (the live Round 1
# Medical result is ~9.5MB) -- a 30s timeout isn't enough to write the
# whole multipart upload, caught posting a real live alert. Uploads get
# their own, much longer timeout; lightweight calls (sendMessage,
# answerCallbackQuery, ...) keep the short one.
UPLOAD_TIMEOUT = 180


def _call(token: str, method: str, files=None, timeout: int = DEFAULT_TIMEOUT, **params):
    url = API_BASE.format(token=token, method=method)
    try:
        resp = requests.post(url, data=params, files=files, timeout=timeout)
        resp.raise_for_status()
    except requests.RequestException as e:
        # Telegram requires the bot token in the URL. requests includes that
        # URL in many exception messages, so never re-emit the original error.
        raise RuntimeError(
            f"Telegram API request failed on {method}: {type(e).__name__}"
        ) from None
    data = resp.json()
    if not data.get("ok"):
        raise RuntimeError(f"Telegram API error on {method}: {data}")
    return data["result"]


def send_message(token: str, chat_id: str, text: str, parse_mode: str = None) -> dict:
    kwargs = {"chat_id": chat_id, "text": text}
    if parse_mode:
        kwargs["parse_mode"] = parse_mode
    return _call(token, "sendMessage", **kwargs)


def send_document(token: str, chat_id: str, file_path: str, caption: str = None) -> dict:
    with open(file_path, "rb") as f:
        kwargs = {"chat_id": chat_id}
        if caption:
            kwargs["caption"] = caption
        return _call(token, "sendDocument", files={"document": f}, timeout=UPLOAD_TIMEOUT, **kwargs)
