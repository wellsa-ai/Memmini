# MemMini

MemMini는 AI 에이전트를 위한 계층형 메모리 라이브러리입니다. 전체
메모리는 L2에 보존하고, L1에는 압축 요약을, L0에는 짧은 라우팅 힌트를
생성해 에이전트가 필요한 컨텍스트만 불러오도록 설계되었습니다.

특정 프레임워크에 묶이지 않습니다. `MemoryCore`를 직접 사용할 수 있고,
어댑터를 통해 에이전트 프레임워크와 연결할 수도 있습니다.

## 주요 기능

- L0/L1/L2 계층형 메모리 모델
- 파일, 벡터, 하이브리드 저장소
- 사용자 또는 에이전트별 네임스페이스 분리
- TTL 기반 만료 및 정리
- positive/negative 키워드 필터
- 비동기 래퍼
- `mini://` 레이어 및 검색 resolver
- LangChain, AutoGen, OpenClaw 어댑터
- 로컬 JSON 및 Markdown 저장소의 원자적 파일 쓰기
- JSONL source reference 기반 symbolic context offload
- 검색 결과의 deterministic `node_id` / `source_ref` 원문 drill-down
- provenance가 포함된 rule-based scenario/persona 추출
- portable `.mv2` snapshot을 위한 선택형 Memvid v2 L2 backend

MemMini는 특정 모델 제공자를 내장하거나 요구하지 않습니다. 기본 계층 생성
경로는 규칙 기반입니다. 모델 기반 요약이 필요한 프로젝트는 `LayerGenerator`
인터페이스에 자체 provider를 주입해 사용할 수 있습니다.

## 설치

```bash
pip install memmini
```

벡터 저장소 의존성:

```bash
pip install "memmini[vector]"
```

선택형 Memvid v2 backend 의존성:

```bash
pip install "memmini[memvid]"
```

프레임워크 어댑터:

```bash
pip install "memmini[langchain]"
pip install "memmini[autogen]"
pip install "memmini[openclaw]"
```

## 빠른 시작

```python
from memmini import open_memory

memory = open_memory(
    "./memory",
    auto_layer_update=False,
)

memory.add(
    "프로젝트 시작: MiniPM-v2는 React와 Node.js를 사용합니다.",
    metadata={"category": "project", "tags": ["minipm"]},
)

memory.update_layers()

print(memory.retrieve(layer="L0"))

for item in memory.search("MiniPM", limit=3):
    print(item["content"])
```

## 원문 추적과 Offload

검색 결과에는 원문으로 돌아갈 수 있는 stable reference가 포함됩니다.

```python
result = memory.search("MiniPM", limit=1)[0]
source = memory.resolve_source_ref(result["source_ref"])
print(source["content"])
```

긴 작업 컨텍스트는 `refs/*.jsonl`로 내리고, agent context에는 compact Mermaid
symbol만 둘 수 있습니다.

```python
offloaded = memory.offload_context(
    "tool failure trace",
    long_tool_output,
)
print(offloaded["mermaid"])
```

L2 원문 기록에서 scenario/persona 후보도 추출할 수 있습니다.

```python
scenarios = memory.extract_scenarios()
persona = memory.extract_persona()
```

이 API들은 namespace 격리, TTL 만료, metadata filter, bounded retrieval 동작을
유지합니다.

## 선택형 Memvid Backend

`MemvidStorage`는 portable single-file snapshot이 필요할 때 선택할 수 있는 L2
backend입니다. MemMini의 L0/L1/context routing API는 그대로 유지하고,
`memvid-sdk`는 `[memvid]` extra를 설치한 경우에만 사용합니다.

```python
from memmini import MemoryCore
from memmini.storage.memvid import MemvidStorage

storage = MemvidStorage("./memory.mv2", backend="auto", enable_hnsw=True)
memory = MemoryCore(storage=storage, auto_layer_update=False)

memory.add("Payment retry policy uses exponential backoff.")
print(memory.search("retry policy")[0]["content"])
print(storage.verify_snapshot()["ok"])
```

`memmini[memvid]`가 없으면 개발과 테스트용 dependency-free Python single-file
snapshot으로 fallback합니다. native bridge는 선택 의존성이고, 기본 설치는
Python-only 상태를 유지합니다.

저장소 백엔드를 직접 구성할 때는 `MemoryCore`를 사용할 수 있습니다.

```python
from memmini import MemoryCore
from memmini.storage.file import FileStorage

memory = MemoryCore(storage=FileStorage(base_path="./memory"))
```

## 저장소 백엔드

| 백엔드 | 패키지 | 용도 |
| --- | --- | --- |
| `FileStorage` | `memmini` | 로컬 JSON 및 Markdown 파일 |
| `VectorStorage` | `memmini[vector]` | ChromaDB 기반 유사도 검색 |
| `HybridStorage` | `memmini[vector]` | 파일 저장과 벡터 검색 결합 |
| `MemvidStorage` | `memmini[memvid]` | 선택형 `.mv2` L2 snapshot backend |

## 계층 모델

| 계층 | 목적 | 일반적인 사용 |
| --- | --- | --- |
| L0 | 짧은 라우팅 힌트 | 더 깊은 컨텍스트가 필요한지 판단 |
| L1 | 압축 요약 | 현재 작업에 필요한 관련 컨텍스트 로드 |
| L2 | 원본 기록 | 전체 소스 메모리 보존 |

## 예제

```bash
python examples/basic_memory.py
python examples/smart_search.py
python examples/provenance_offload.py
python examples/memvid_backend.py
python examples/vector_storage.py
```

`examples/vector_storage.py`는 `pip install "memmini[vector]"`가 필요합니다.
`examples/memvid_backend.py`는 `pip install "memmini[memvid]"`가 있으면 native
backend를 사용합니다.

## 어댑터

```python
from memmini import MemoryCore
from memmini.adapters import LangChainAdapter
from memmini.storage.file import FileStorage

core = MemoryCore(storage=FileStorage(base_path="./memory"))
adapter = LangChainAdapter(core)

history = adapter.load_memory_variables({})["history"]
```

## 라이선스

MemMini는 MIT License로 배포됩니다.
