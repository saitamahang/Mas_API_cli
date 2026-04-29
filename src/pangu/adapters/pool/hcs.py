from __future__ import annotations

from pangu.adapters.base import PoolAdapter, PoolRequest


class PoolAdapterHCS(PoolAdapter):
    """
    HCS 环境（标准 API 3.15.1）
    POST /v1/{project_id}/pangu/studio/resource-pool/online/{workspace_id}/pool
    workspace_id 在路径中，响应为深层嵌套结构。
    """

    workspace_in_path = True
    path = "/v1/{project_id}/pangu/studio/resource-pool/online/{workspace_id}/pool"

    def build_request(self, req: PoolRequest) -> dict:
        body: dict = {"arch": req.arch}
        if req.device_type:
            body["device_type"] = req.device_type
        if req.job_type:
            body["job_type"] = req.job_type
        if req.status:
            body["status"] = req.status
        if req.chip_types:
            body["chip_types"] = req.chip_types
        return body

    def normalize(self, data: dict) -> list[dict]:
        raw_pools = data.get("pools") or []
        result = []
        for p in raw_pools:
            metadata = p.get("metadata") or {}
            labels   = metadata.get("labels") or {}
            spec     = p.get("spec") or {}
            status   = p.get("status") or {}
            nodes    = p.get("nodes") or []
            resources = spec.get("resources") or []

            node_count = len(nodes) or sum(r.get("count", 0) for r in resources)

            # HCS resources 列表中可能含 flavor_id（如 "modelarts.pool.visual.8xlarge"）
            flavor_id = ""
            if resources:
                flavor_id = resources[0].get("flavor_id") or resources[0].get("flavor", "")

            result.append({
                "pool_id":    metadata.get("name", ""),
                "pool_name":  labels.get("os.modelarts/name", ""),
                "pool_type":  spec.get("type", ""),
                "status":     status.get("phase", ""),
                "scope":      "/".join(spec.get("scope") or []),
                "node_count": node_count,
                "chip_type":  p.get("chip_type", ""),
                "flavor_id":  flavor_id,
                "arch":       p.get("arch", ""),
                "create_time": metadata.get("creationTimestamp", ""),
            })
        return result
