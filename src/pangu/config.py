"""配置管理模块 - 读写 ~/.pangu/config.yaml"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Optional

import yaml
from pydantic import BaseModel, Field


CONFIG_DIR = Path.home() / ".pangu"
CONFIG_FILE = CONFIG_DIR / "config.yaml"
TOKEN_CACHE_FILE = CONFIG_DIR / "token_cache.yaml"


class PanguConfig(BaseModel):
    """盘古 CLI 全局配置"""

    # 环境连接
    endpoint: str = Field(default="", description="盘古服务外部 APIG 域名")
    iam_endpoint: str = Field(default="", description="IAM 认证域名")

    # 身份信息
    auth_mode: str = Field(default="token", description="认证模式: token | apikey")
    username: str = Field(default="", description="用户名")
    domain_name: str = Field(default="", description="租户名")
    project_name: str = Field(default="", description="项目名称")
    project_id: str = Field(default="", description="项目 ID")

    # 默认上下文
    default_workspace_id: str = Field(default="", description="默认工作空间 ID")

    # API Key 模式
    api_key: str = Field(default="", description="API Key (X-Apig-AppCode)")

    # 网络
    ssl_verify: bool = Field(default=True, description="是否验证 SSL 证书")
    timeout: int = Field(default=60, description="HTTP 请求超时秒数")

    @classmethod
    def load(cls) -> "PanguConfig":
        """从配置文件加载，不存在则返回默认值"""
        if CONFIG_FILE.exists():
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            return cls(**data)
        return cls()

    def save(self) -> None:
        """保存到配置文件"""
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            yaml.dump(
                self.model_dump(),
                f,
                default_flow_style=False,
                allow_unicode=True,
            )

    def get(self, key: str) -> Any:
        """获取配置值"""
        return getattr(self, key, None)

    def set(self, key: str, value: Any) -> None:
        """设置配置值"""
        if not hasattr(self, key):
            raise KeyError(f"未知配置项: {key}")
        # 类型转换
        field_info = self.model_fields[key]
        if field_info.annotation is bool:
            value = str(value).lower() in ("true", "1", "yes")
        elif field_info.annotation is int:
            value = int(value)
        setattr(self, key, value)

    def validate_required(self, *keys: str) -> list[str]:
        """检查必要配置是否已设置，返回缺失的 key 列表"""
        missing = []
        for key in keys:
            val = self.get(key)
            if val is None or val == "":
                missing.append(key)
        return missing

    def get_workspace_id(self, workspace_id: Optional[str] = None) -> str:
        """获取 workspace_id: 命令行参数 > 配置默认值"""
        wid = workspace_id or self.default_workspace_id
        if not wid:
            raise ValueError(
                "未指定 workspace_id。请通过 --workspace 参数传入，"
                "或运行 pangu config set default_workspace_id <id>"
            )
        return wid
