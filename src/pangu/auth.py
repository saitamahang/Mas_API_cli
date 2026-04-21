"""认证模块 - Token 获取、缓存、刷新，API Key 认证"""

from __future__ import annotations

import getpass
import os
from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx
import yaml

from pangu.config import CONFIG_DIR, TOKEN_CACHE_FILE, PanguConfig


class TokenCache:
    """Token 缓存管理"""

    def __init__(self, token: str = "", expires_at: str = ""):
        self.token = token
        self.expires_at = expires_at

    @classmethod
    def load(cls) -> "TokenCache":
        if TOKEN_CACHE_FILE.exists():
            with open(TOKEN_CACHE_FILE, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            return cls(**data)
        return cls()

    def save(self) -> None:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        with open(TOKEN_CACHE_FILE, "w", encoding="utf-8") as f:
            yaml.dump(
                {"token": self.token, "expires_at": self.expires_at},
                f,
                default_flow_style=False,
            )

    def is_valid(self) -> bool:
        if not self.token or not self.expires_at:
            return False
        try:
            exp = datetime.fromisoformat(self.expires_at)
            # 提前 5 分钟视为过期
            return datetime.now(timezone.utc) < exp - timedelta(minutes=5)
        except (ValueError, TypeError):
            return False

    def remaining(self) -> str:
        """返回剩余有效时间的可读字符串"""
        if not self.is_valid():
            return "已过期"
        exp = datetime.fromisoformat(self.expires_at)
        delta = exp - datetime.now(timezone.utc)
        hours, remainder = divmod(int(delta.total_seconds()), 3600)
        minutes = remainder // 60
        return f"{hours}h{minutes}m"


class AuthManager:
    """认证管理器"""

    def __init__(self, config: PanguConfig):
        self.config = config
        self._token_cache = TokenCache.load()

    def get_auth_headers(self) -> dict[str, str]:
        """获取认证请求头"""
        if self.config.auth_mode == "apikey":
            if not self.config.api_key:
                raise ValueError(
                    "API Key 未配置。请运行: pangu config set api_key <key>"
                )
            return {
                "X-Apig-AppCode": self.config.api_key,
                "Content-Type": "application/json",
            }

        # Token 模式
        token = self.get_token()
        return {
            "X-Auth-Token": token,
            "Content-Type": "application/json",
        }

    def get_token(self) -> str:
        """获取有效 Token，过期则自动刷新"""
        if self._token_cache.is_valid():
            return self._token_cache.token

        raise ValueError(
            "Token 未获取或已过期。请运行: pangu auth login"
        )

    def login(self, password: Optional[str] = None) -> str:
        """通过 IAM 获取 Token"""
        cfg = self.config
        missing = cfg.validate_required(
            "iam_endpoint", "username", "domain_name", "project_name"
        )
        if missing:
            raise ValueError(
                f"缺少认证配置: {', '.join(missing)}。"
                f"请先运行 pangu config set <key> <value>"
            )

        # 密码优先级: 参数 > 环境变量 > 交互输入
        if password is None:
            password = os.environ.get("PANGU_PASSWORD")
        if password is None:
            password = getpass.getpass(f"请输入 {cfg.username} 的密码: ")

        url = f"https://{cfg.iam_endpoint}/v3/auth/tokens"
        payload = {
            "auth": {
                "identity": {
                    "methods": ["password"],
                    "password": {
                        "user": {
                            "name": cfg.username,
                            "password": password,
                            "domain": {"name": cfg.domain_name},
                        }
                    },
                },
                "scope": {
                    "project": {"name": cfg.project_name}
                },
            }
        }

        resp = httpx.post(
            url,
            json=payload,
            verify=cfg.ssl_verify,
            timeout=cfg.timeout,
        )

        if resp.status_code != 201:
            body = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
            error_msg = body.get("error_msg", resp.text)
            raise RuntimeError(f"Token 获取失败 [{resp.status_code}]: {error_msg}")

        token = resp.headers.get("X-Subject-Token", "")
        if not token:
            raise RuntimeError("响应中未找到 X-Subject-Token")

        # Token 有效期 24 小时
        expires_at = (
            datetime.now(timezone.utc) + timedelta(hours=24)
        ).isoformat()

        self._token_cache = TokenCache(token=token, expires_at=expires_at)
        self._token_cache.save()

        return token

    def status(self) -> dict:
        """返回当前认证状态"""
        if self.config.auth_mode == "apikey":
            return {
                "mode": "apikey",
                "configured": bool(self.config.api_key),
            }
        return {
            "mode": "token",
            "valid": self._token_cache.is_valid(),
            "remaining": self._token_cache.remaining(),
        }
