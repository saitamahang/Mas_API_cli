"""HTTP 客户端封装 - 路径变量替换、认证注入、统一错误处理"""

from __future__ import annotations

import sys
import time
from typing import Any, Callable, Optional

import httpx
from rich.console import Console

from pangu.auth import AuthManager
from pangu.config import PanguConfig

console = Console(stderr=True)


class APIError(Exception):
    """API 调用错误"""

    def __init__(self, status_code: int, error_code: str, error_msg: str):
        self.status_code = status_code
        self.error_code = error_code
        self.error_msg = error_msg
        super().__init__(f"[{status_code}] {error_code}: {error_msg}")


class PanguClient:
    """盘古 API 统一客户端"""

    def __init__(
        self,
        config: Optional[PanguConfig] = None,
        auth: Optional[AuthManager] = None,
    ):
        self.config = config or PanguConfig.load()
        self.auth = auth or AuthManager(self.config)
        self._http = httpx.Client(
            verify=self.config.ssl_verify,
            timeout=self.config.timeout,
        )

    def _build_url(self, path: str, **path_params: str) -> str:
        """拼接完整 URL，替换路径变量"""
        # 自动填充 project_id
        if "{project_id}" in path and "project_id" not in path_params:
            if not self.config.project_id:
                raise ValueError(
                    "project_id 未配置。请运行: pangu config set project_id <id>"
                )
            path_params["project_id"] = self.config.project_id

        # 替换路径变量
        for key, value in path_params.items():
            path = path.replace(f"{{{key}}}", value)

        endpoint = self.config.endpoint
        if not endpoint:
            raise ValueError(
                "endpoint 未配置。请运行: pangu config set endpoint <域名>"
            )

        return f"https://{endpoint}{path}"

    def _handle_response(self, resp: httpx.Response) -> Any:
        """统一处理响应"""
        if resp.status_code in (200, 201):
            content_type = resp.headers.get("content-type", "")
            if "application/json" in content_type:
                return resp.json()
            # 有些接口返回纯文本 "ok"
            text = resp.text.strip()
            if text:
                return text
            return None

        # 错误处理
        error_code = ""
        error_msg = resp.text
        try:
            body = resp.json()
            error_code = body.get("error_code", "")
            error_msg = body.get("error_msg", resp.text)
        except Exception:
            pass

        raise APIError(resp.status_code, error_code, error_msg)

    def request(
        self,
        method: str,
        path: str,
        workspace_id: Optional[str] = None,
        params: Optional[dict] = None,
        json: Optional[dict] = None,
        **path_params: str,
    ) -> Any:
        """发起 API 请求

        Args:
            method: HTTP 方法
            path: API 路径，如 /v1/{project_id}/workspaces
            workspace_id: 工作空间 ID，传入则替换路径中的 {workspace_id}
            params: Query 参数
            json: 请求体
            **path_params: 额外路径变量
        """
        # 处理 workspace_id
        if "{workspace_id}" in path:
            wid = self.config.get_workspace_id(workspace_id)
            path_params["workspace_id"] = wid

        url = self._build_url(path, **path_params)
        headers = self.auth.get_auth_headers()

        # 过滤 None 值的 query 参数
        if params:
            params = {k: v for k, v in params.items() if v is not None}

        resp = self._http.request(
            method=method,
            url=url,
            headers=headers,
            params=params,
            json=json,
        )

        return self._handle_response(resp)

    def get(self, path: str, workspace_id: Optional[str] = None, params: Optional[dict] = None, **kw: str) -> Any:
        return self.request("GET", path, workspace_id=workspace_id, params=params, **kw)

    def post(self, path: str, workspace_id: Optional[str] = None, json: Optional[dict] = None, **kw: str) -> Any:
        return self.request("POST", path, workspace_id=workspace_id, json=json, **kw)

    def put(self, path: str, workspace_id: Optional[str] = None, json: Optional[dict] = None, **kw: str) -> Any:
        return self.request("PUT", path, workspace_id=workspace_id, json=json, **kw)

    def delete(self, path: str, workspace_id: Optional[str] = None, params: Optional[dict] = None, **kw: str) -> Any:
        return self.request("DELETE", path, workspace_id=workspace_id, params=params, **kw)

    def wait_for_status(
        self,
        poll_fn: Callable[[], dict],
        target_statuses: set[str],
        failure_statuses: set[str] | None = None,
        status_key: str = "status",
        interval: int = 10,
        timeout: int = 3600,
    ) -> dict:
        """轮询等待资源达到目标状态

        Args:
            poll_fn: 轮询函数，返回资源详情 dict
            target_statuses: 目标状态集合
            failure_statuses: 失败状态集合
            status_key: 状态字段名
            interval: 轮询间隔秒数
            timeout: 超时秒数
        """
        failure_statuses = failure_statuses or {"failed"}
        start = time.time()

        while True:
            result = poll_fn()
            current = result.get(status_key, "")

            if current in target_statuses:
                console.print(f"[green]状态已达到: {current}[/green]")
                return result

            if current in failure_statuses:
                console.print(f"[red]任务失败: {current}[/red]")
                raise RuntimeError(f"资源进入失败状态: {current}")

            elapsed = time.time() - start
            if elapsed > timeout:
                raise TimeoutError(
                    f"等待超时 ({timeout}s)，当前状态: {current}"
                )

            console.print(
                f"  当前状态: {current}，"
                f"已等待 {int(elapsed)}s，"
                f"每 {interval}s 轮询...",
                highlight=False,
            )
            time.sleep(interval)
