from pangu.adapters.pool.hcs import PoolAdapterHCS
from pangu.adapters.pool.hc import PoolAdapterHC

_POOL_REGISTRY = {
    "HCS": PoolAdapterHCS,
    "HC":  PoolAdapterHC,
}


def get_pool_adapter(env_type: str = "HCS"):
    cls = _POOL_REGISTRY.get(env_type)
    if cls is None:
        raise ValueError(
            f"不支持的 env_type: {env_type}，可选: {list(_POOL_REGISTRY)}"
        )
    return cls()
