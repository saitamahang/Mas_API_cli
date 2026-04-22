from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class PoolRequest:
    """跨版本统一的请求参数容器，各 Adapter 按需取用"""
    # v1
    arch: str = "X86"
    device_type: Optional[str] = None
    status: Optional[str] = None
    # v2
    job_type: Optional[str] = None
    chip_types: Optional[List[str]] = field(default=None)
    use_type: Optional[str] = None
    flavor_ids: Optional[List[str]] = field(default=None)
    asset_code: Optional[str] = None


class PoolAdapter(ABC):
    """资源池 Adapter 抽象基类"""

    # 子类设为 False 时，workspace_id 通过 header 传递而非路径变量
    workspace_in_path: bool = True

    @property
    @abstractmethod
    def path(self) -> str:
        """API 路径（含路径变量）"""
        ...

    def extra_headers(self, workspace_id: str) -> dict:
        """workspace 不在路径中时，由此返回额外 header"""
        return {}

    @abstractmethod
    def build_request(self, req: PoolRequest) -> dict:
        """将 PoolRequest 转换为实际请求 body"""
        ...

    @abstractmethod
    def normalize(self, data: dict) -> list[dict]:
        """将 API 响应拍平为统一结构:
        [{"pool_id", "pool_name", "pool_type", "status",
          "scope", "node_count", "chip_type", "create_time", ...}]
        """
        ...
