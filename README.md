# MemMini

MemMini is a Python library for layered memory in AI agents. It stores full
memory records in L2, generates compact summaries in L1, and keeps short routing
hints in L0 so an agent can load only the context it needs.

The package is framework-neutral. It can be used directly through `MemoryCore`
or connected to agent frameworks through adapters.

## Features

- L0/L1/L2 layered memory model
- File, vector, and hybrid storage backends
- Namespace isolation for multiple users or agents
- TTL-based expiration and cleanup
- Positive and negative keyword filters
- Async wrapper
- `mini://` resolver for layer and search references
- LangChain, AutoGen, and OpenClaw adapters
- Atomic file writes for local JSON and Markdown storage
- Symbolic context offload with JSONL source references
- Deterministic `node_id` / `source_ref` drill-down for search results
- Rule-based scenario and persona extraction with provenance
- Optional Memvid v2 L2 backend for portable `.mv2` snapshots

MemMini does not bundle or require a model provider. The default layer
generation path is rule-based. Projects that want model-generated summaries can
inject their own provider through the `LayerGenerator` interface.

## Installation

```bash
pip install memmini
```

Optional vector storage dependencies:

```bash
pip install "memmini[vector]"
```

Optional Memvid v2 backend dependencies:

```bash
pip install "memmini[memvid]"
```

Optional framework adapters:

```bash
pip install "memmini[langchain]"
pip install "memmini[autogen]"
pip install "memmini[openclaw]"
```

## Quick Start

```python
from memmini import open_memory

memory = open_memory(
    "./memory",
    auto_layer_update=False,
)

memory.add(
    "Project started: MiniPM-v2 uses React and Node.js.",
    metadata={"category": "project", "tags": ["minipm"]},
)

memory.update_layers()

print(memory.retrieve(layer="L0"))

for item in memory.search("MiniPM", limit=3):
    print(item["content"])
```

## Provenance and Offload

Search results include stable references back to the source record:

```python
result = memory.search("MiniPM", limit=1)[0]
source = memory.resolve_source_ref(result["source_ref"])
print(source["content"])
```

Verbose task context can be offloaded to `refs/*.jsonl` while the agent keeps a
compact Mermaid symbol in context:

```python
offloaded = memory.offload_context(
    "tool failure trace",
    long_tool_output,
)
print(offloaded["mermaid"])
```

MemMini can also extract scenario and persona candidates from L2 records:

```python
scenarios = memory.extract_scenarios()
persona = memory.extract_persona()
```

These APIs keep namespace isolation, TTL expiry, metadata filters, and bounded
retrieval behavior intact.

## Optional Memvid Backend

`MemvidStorage` can be used as an optional L2 backend when you want a portable
single-file snapshot. It keeps MemMini's L0/L1/context routing API intact and
uses `memvid-sdk` only when installed through the `[memvid]` extra.

```python
from memmini import MemoryCore
from memmini.storage.memvid import MemvidStorage

storage = MemvidStorage("./memory.mv2", backend="auto", enable_hnsw=True)
memory = MemoryCore(storage=storage, auto_layer_update=False)

memory.add("Payment retry policy uses exponential backoff.")
print(memory.search("retry policy")[0]["content"])
print(storage.verify_snapshot()["ok"])
```

Without `memmini[memvid]`, the backend falls back to a dependency-free Python
single-file snapshot for local development and tests. The native bridge uses
Memvid v2 as an optional dependency; MemMini's default install remains
Python-only.

For custom storage backends, instantiate `MemoryCore` directly:

```python
from memmini import MemoryCore
from memmini.storage.file import FileStorage

memory = MemoryCore(storage=FileStorage(base_path="./memory"))
```

## Storage Backends

| Backend | Package | Use case |
| --- | --- | --- |
| `FileStorage` | `memmini` | Local JSON and Markdown files |
| `VectorStorage` | `memmini[vector]` | ChromaDB-backed similarity search |
| `HybridStorage` | `memmini[vector]` | File persistence with vector search |
| `MemvidStorage` | `memmini[memvid]` | Optional `.mv2` L2 snapshot backend |

## Layer Model

| Layer | Purpose | Typical use |
| --- | --- | --- |
| L0 | Short routing hints | Decide whether deeper context is needed |
| L1 | Compact summaries | Load relevant context for the current task |
| L2 | Original records | Preserve full source memory |

## Examples

```bash
python examples/basic_memory.py
python examples/smart_search.py
python examples/provenance_offload.py
python examples/memvid_backend.py
python examples/vector_storage.py
```

`examples/vector_storage.py` requires `pip install "memmini[vector]"`.
`examples/memvid_backend.py` uses the native backend when
`pip install "memmini[memvid]"` is available.

## Adapters

```python
from memmini import MemoryCore
from memmini.adapters import LangChainAdapter
from memmini.storage.file import FileStorage

core = MemoryCore(storage=FileStorage(base_path="./memory"))
adapter = LangChainAdapter(core)

history = adapter.load_memory_variables({})["history"]
```

## License

MemMini is released under the MIT License.
