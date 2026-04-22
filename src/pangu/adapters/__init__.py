from pangu.adapters.pool.v1 import PoolAdapterV1
from pangu.adapters.pool.v2 import PoolAdapterV2

_POOL_REGISTRY = {
    "HCS": PoolAdapterV1,
    "HC":  PoolAdapterV2,
}


def get_pool_adapter(env_type: str = "HCS"):
    cls = _POOL_REGISTRY.get(env_type)
    if cls is None:
        raise ValueError(
            f"不支持的 env_type: {env_type}，可选: {list(_POOL_REGISTRY)}"
        )
    return cls()
