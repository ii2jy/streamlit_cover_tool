from __future__ import annotations

import os
import socket
from dataclasses import dataclass

from openai import (
    APIConnectionError,
    APITimeoutError,
    AuthenticationError,
    BadRequestError,
    DefaultHttpxClient,
    OpenAI,
    PermissionDeniedError,
    RateLimitError,
)


COMMON_LOCAL_PROXY_PORTS = (7897, 7890, 10809, 1080)


@dataclass(frozen=True)
class AIConnectionConfig:
    proxy_url: str | None
    base_url: str | None
    source: str


def _port_is_open(port: int, timeout: float = 0.15) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=timeout):
            return True
    except OSError:
        return False


def resolve_connection_config() -> AIConnectionConfig:
    """Resolve proxy/base URL without hard-coding a provider or secret.

    Explicit environment settings win. If none exist, common loopback proxy ports
    are detected so the desktop tool works with Clash/V2Ray-style system clients.
    """
    base_url = os.getenv("OPENAI_BASE_URL") or None
    explicit_proxy = (
        os.getenv("OPENAI_PROXY")
        or os.getenv("HTTPS_PROXY")
        or os.getenv("HTTP_PROXY")
        or os.getenv("ALL_PROXY")
    )
    if explicit_proxy:
        return AIConnectionConfig(explicit_proxy, base_url, "环境变量代理")

    for port in COMMON_LOCAL_PROXY_PORTS:
        if _port_is_open(port):
            return AIConnectionConfig(
                f"http://127.0.0.1:{port}", base_url, f"自动发现本地代理 {port}"
            )
    return AIConnectionConfig(None, base_url, "直连")


def create_openai_client(
    api_key: str,
    client_class: type[OpenAI] = OpenAI,
    timeout_seconds: float = 90.0,
) -> OpenAI:
    config = resolve_connection_config()
    kwargs: dict[str, object] = {
        "api_key": api_key,
        "timeout": timeout_seconds,
        "max_retries": 3,
    }
    if config.base_url:
        kwargs["base_url"] = config.base_url
    if config.proxy_url:
        kwargs["http_client"] = DefaultHttpxClient(proxy=config.proxy_url)
    return client_class(**kwargs)


def connection_label() -> str:
    return resolve_connection_config().source


def friendly_openai_error(exc: Exception) -> str:
    if isinstance(exc, APIConnectionError):
        return (
            "无法连接 OpenAI API。请确认代理/VPN仍在运行；"
            "如果代理端口不是 7897、7890、10809 或 1080，请设置 OPENAI_PROXY。"
        )
    if isinstance(exc, APITimeoutError):
        return "AI 请求超时。请保持代理/VPN开启后重试，或先换用体积更小的图片。"
    if isinstance(exc, AuthenticationError):
        return "API Key 无效或已失效，请在 .streamlit/secrets.toml 中更新 OPENAI_API_KEY。"
    if isinstance(exc, RateLimitError):
        return "API 调用额度不足或请求过快，请检查账户余额并稍后重试。"
    if isinstance(exc, PermissionDeniedError):
        return "当前 API Key 没有使用所选模型的权限，请检查项目权限或更换模型。"
    if isinstance(exc, BadRequestError):
        return f"AI 未接受本次输入：{exc.message}"
    return f"AI 调用失败：{exc}"
