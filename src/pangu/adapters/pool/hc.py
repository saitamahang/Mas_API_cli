from __future__ import annotations

from pangu.adapters.base import PoolAdapter, PoolRequest

# processor_type 整数编码转可读字符串
_PROCESSOR_TYPE = {0: "NPU", 1: "GPU", 2: "Other"}


class PoolAdapterHC(PoolAdapter):
    """
    HC 环境
    POST /v1/{project_id}/pangu/studio/resource-pool/pool-list
    workspace_id 通过 Header Studio-Workspace-ID 传递（可选）。
    响应为平铺结构，字段命名与 HCS 不同。

    已知问题（待接口方确认）：
    - 响应 key 疑似 typo：finetunePoolListList，同时兼容 finetunePoolList
    - availableResourceNum 为 camelCase，其余字段为 snake_case
    """

    workspace_in_path = False
    path = "/v1/{project_id}/pangu/studio/resource-pool/pool-list"

    def extra_headers(self, workspace_id: str) -> dict:
        if workspace_id:
            return {"Studio-Workspace-ID": workspace_id}
        return {}

    def build_request(self, req: PoolRequest) -> dict:
        body: dict = {}
        # 三个 API 必填字段，未传则由 API 返回错误，保留原始错误信息
        if req.job_type is not None:
            body["job_type"] = req.job_type
        if req.chip_types is not None:
            body["chip_types"] = req.chip_types
        if req.use_type is not None:
            body["use_type"] = req.use_type
        # 可选字段
        if req.flavor_ids:
            body["flavor_ids"] = req.flavor_ids
        if req.asset_code:
            body["asset_code"] = req.asset_code
        return body

    def normalize(self, data: dict) -> list[dict]:
        # 兼容文档 typo：finetunePoolListList / finetunePoolList
        raw = (
            data.get("finetunePoolListList")
            or data.get("finetunePoolList")
            or data.get("pools")
            or []
        )
        result = []
        for p in raw:
            proc_int = p.get("processor_type")
            proc_str = _PROCESSOR_TYPE.get(proc_int, str(proc_int)) if proc_int is not None else ""

            result.append({
                "pool_id":    p.get("pool_id", ""),
                "pool_name":  p.get("pool_name", ""),
                "pool_type":  p.get("use_type", ""),       # HC 无 type，用 use_type 替代
                "status":     p.get("pool_status", ""),    # HCS: phase，HC: pool_status
                "scope":      p.get("job_type", ""),       # HC 单值
                "node_count": p.get("node_count", 0),
                "chip_type":  p.get("chip_type", ""),
                "flavor_id":  p.get("flavor_id", ""),      # HC 创建训练任务时需要
                "arch":        "",                          # HC 无 arch 字段
                "create_time": p.get("create_time", ""),
                # HC 额外字段
                "processor":  proc_str,
                "proc_version": p.get("processor_version", ""),
                "available":   p.get("availableResourceNum", ""),  # camelCase，HC 接口命名不一致
                "description": p.get("description", ""),
            })
        return result
