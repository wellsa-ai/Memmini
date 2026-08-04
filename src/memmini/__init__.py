"""
MemMini - L0/L1/L2 계층형 메모리 시스템

Load only the memory layer you need to reduce context tokens.
"""

__version__ = "0.4.0"

from memmini.core.async_core import AsyncMemoryCore
from memmini.core.layer_generator import LayerGenerator
from memmini.core.memory_core import MemoryCore
from memmini.core.relationship import Relationship, RelationType
from memmini.core.storage import MemoryStorage
from memmini.storage.file import FileStorage


def open_memory(
    path: str = "~/.memmini",
    *,
    namespace: str = "default",
    auto_layer_update: bool = True,
    auto_layer_interval: int = 0,
    cache_ttl: int = 3600,
) -> MemoryCore:
    """Open a file-backed MemMini memory store.

    This is the shortest entry point for local use. Projects that need a custom
    storage backend can instantiate ``MemoryCore`` directly.
    """
    return MemoryCore.from_path(
        path,
        namespace=namespace,
        auto_layer_update=auto_layer_update,
        auto_layer_interval=auto_layer_interval,
        cache_ttl=cache_ttl,
    )


__all__ = [
    "AsyncMemoryCore",
    "MemoryCore",
    "MemoryStorage",
    "FileStorage",
    "LayerGenerator",
    "Relationship",
    "RelationType",
    "open_memory",
    "__version__",
]
