"""
Optional MemvidStorage example.

Install the native bridge with:
    pip install "memmini[memvid]"

Without the extra, MemvidStorage falls back to a dependency-free Python
single-file snapshot so this example still runs.
"""

from pathlib import Path
from tempfile import TemporaryDirectory

from memmini import MemoryCore
from memmini.storage.memvid import MemvidStorage

with TemporaryDirectory() as tmp:
    storage = MemvidStorage(
        str(Path(tmp) / "memory.mv2"),
        backend="auto",
        enable_hnsw=False,
    )
    memory = MemoryCore(storage=storage, auto_layer_update=False)

    memory.add(
        "Payment retry policy uses exponential backoff.",
        metadata={"category": "payments", "priority": "high"},
    )
    result = memory.search("retry policy", limit=1)[0]
    restored = storage.restore_to(str(Path(tmp) / "portable-copy.mv2"))

    print(storage.backend)
    print(result["content"])
    print(restored.search("retry policy", limit=1)[0]["content"])
