"""
MemMini Memvid Storage

Optional L2 backend inspired by Memvid v2.  The default MemMini install does
not import or require memvid-sdk; installing ``memmini[memvid]`` enables the
native .mv2 bridge.  Without the extra this class uses a Python single-file
snapshot with embedded frames and WAL so MemMini's storage contract remains
testable and portable.
"""

import hashlib
import importlib
import json
import math
import os
import re
import shutil
import tempfile
import uuid
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union, cast

from memmini.core.relationship import Relationship, RelationType
from memmini.core.storage import MemoryStorage


class MemvidStorage(MemoryStorage):
    """Optional single-file Memvid-style storage backend.

    Args:
        path: ``.mv2`` snapshot path.
        backend: ``"auto"``, ``"sdk"``, or ``"python"``. ``"auto"`` uses
            memvid-sdk when importable and falls back to the Python snapshot.
        enable_bm25: Enable lexical BM25 scoring.
        enable_hnsw: Request native HNSW/vector search when memvid-sdk is used.

    The Python fallback is deliberately dependency-free. It is not a replacement
    for Memvid v2's Rust implementation; it preserves MemMini semantics and
    provides deterministic PoC coverage when the optional FFI wheel is absent.
    """

    _FORMAT = "memmini-memvid-adapter"
    _FORMAT_VERSION = 1
    _SDK_RECORD_KEY = "_memmini_record"
    _SDK_OP_KEY = "_memmini_op"

    def __init__(
        self,
        path: str = "~/.memmini/memmini.mv2",
        *,
        backend: str = "auto",
        enable_bm25: bool = True,
        enable_hnsw: bool = False,
    ) -> None:
        if backend not in {"auto", "sdk", "python"}:
            raise ValueError("backend는 'auto', 'sdk', 'python' 중 하나여야 합니다")

        self.path = Path(path).expanduser()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.enable_bm25 = enable_bm25
        self.enable_hnsw = enable_hnsw
        self._backend_preference = backend
        self._backend = "python"
        self._sdk: Any = None
        self._sdk_handle: Any = None
        self._sdk_embedder: Any = None

        if backend in {"auto", "sdk"}:
            try:
                self._open_sdk()
            except ImportError:
                if backend == "sdk":
                    raise

        if self._backend == "python" and not self.path.exists():
            self._write_state(self._empty_state())

    @property
    def backend(self) -> str:
        """현재 활성 backend 이름."""
        return self._backend

    def close(self) -> None:
        """Close the native SDK handle when present."""
        if self._sdk_handle is not None:
            close = getattr(self._sdk_handle, "close", None)
            if callable(close):
                close()
            self._sdk_handle = None

    def save(
        self,
        content: Union[str, Dict],
        metadata: Dict,
        namespace: str = "default",
    ) -> str:
        """Store an L2 memory record."""
        self._validate_namespace(namespace)
        memory_id = f"mem-{uuid.uuid4()}"
        metadata = dict(metadata)
        created_at = datetime.now().isoformat()
        node_id = str(
            metadata.get("node_id") or f"node_{memory_id.removeprefix('mem-')}"
        )
        source_ref = str(
            metadata.get("source_ref") or f"{namespace}/L2/{memory_id}.mv2"
        )
        metadata.setdefault("node_id", node_id)
        metadata.setdefault("source_ref", source_ref)

        record = self._memory_record(
            memory_id=memory_id,
            content=content,
            metadata=metadata,
            namespace=namespace,
            created_at=created_at,
            node_id=node_id,
            source_ref=source_ref,
        )
        self._append_record("save", record)
        return memory_id

    def get(self, memory_id: str, namespace: str = "default") -> Optional[Dict]:
        """Retrieve the current L2 record for ``memory_id``."""
        self._validate_namespace(namespace)
        for record in self.get_all_raw(namespace=namespace):
            if record.get("id") == memory_id:
                return record
        return None

    def update(
        self,
        memory_id: str,
        content: Union[str, Dict],
        metadata: Optional[Dict] = None,
        namespace: str = "default",
    ) -> bool:
        """Append an immutable update frame and make it current."""
        existing = self.get(memory_id, namespace)
        if not existing:
            return False

        existing_metadata = dict(existing.get("metadata", {}))
        if metadata is not None:
            existing_metadata = dict(metadata)
        existing_metadata["updated_at"] = datetime.now().isoformat()
        existing_metadata["version"] = (
            existing.get("metadata", {}).get("version", 0) + 1
        )
        record = self._memory_record(
            memory_id=memory_id,
            content=content,
            metadata=existing_metadata,
            namespace=namespace,
            created_at=str(existing.get("created_at") or datetime.now().isoformat()),
            node_id=str(
                existing.get("node_id") or existing_metadata.get("node_id", "")
            ),
            source_ref=str(
                existing.get("source_ref") or existing_metadata.get("source_ref", "")
            ),
        )
        if "expires_at" in existing:
            record["expires_at"] = existing["expires_at"]
        self._append_record("update", record)
        return True

    def delete(self, memory_id: str, namespace: str = "default") -> bool:
        """Append a tombstone frame."""
        existing = self.get(memory_id, namespace)
        if not existing:
            return False
        self._append_record("delete", existing)
        return True

    def search(
        self,
        query: str,
        layer: str = "L1",
        limit: int = 5,
        filters: Optional[Dict] = None,
        positive: Optional[List[str]] = None,
        negative: Optional[List[str]] = None,
        namespace: str = "default",
    ) -> List[Dict]:
        """Search current L2 records using native Memvid or deterministic hybrid."""
        self._validate_namespace(namespace)
        if self._backend == "sdk" and query.strip():
            native_results = self._search_sdk(
                query=query,
                limit=limit,
                filters=filters,
                positive=positive,
                negative=negative,
                namespace=namespace,
            )
            if native_results:
                return native_results

        return self._search_python(
            query=query,
            limit=limit,
            filters=filters,
            positive=positive,
            negative=negative,
            namespace=namespace,
        )

    def get_layer(
        self,
        layer: str,
        time_range: Optional[tuple] = None,
        namespace: str = "default",
    ) -> str:
        """Load L0/L1 text from the same snapshot file."""
        self._validate_namespace(namespace)
        if layer not in {"L0", "L1"}:
            raise ValueError("get_layer는 L0/L1만 지원 (L2는 get_all 사용)")
        if self._backend == "sdk":
            return self._get_sdk_layer(layer, namespace)

        state = self._read_state()
        ns = self._namespace_state(state, namespace)
        layers = cast(Dict[str, str], ns.setdefault("layers", {}))
        return layers.get(layer, "")

    def save_layer(self, layer: str, content: str, namespace: str = "default") -> None:
        """Save L0/L1 text into the same snapshot file."""
        self._validate_namespace(namespace)
        if layer not in {"L0", "L1"}:
            raise ValueError("save_layer는 L0/L1만 지원")
        if self._backend == "sdk":
            record = {
                "type": "layer",
                "layer": layer,
                "content": content,
                "namespace": namespace,
                "created_at": datetime.now().isoformat(),
            }
            self._put_sdk_payload(
                uri=f"mv2://{namespace}/layers/{layer}/{self._next_sdk_seq()}",
                title=f"{namespace}:{layer}",
                text=content or f"{layer} empty",
                record=record,
                op="layer",
            )
            return

        state = self._read_state()
        ns = self._namespace_state(state, namespace)
        layers = cast(Dict[str, str], ns.setdefault("layers", {}))
        layers[layer] = content
        self._append_python_frame(
            state=state,
            op="layer",
            namespace=namespace,
            memory_id=f"layer-{layer}",
            record={"layer": layer, "content": content, "namespace": namespace},
        )
        self._write_state(state)

    def get_all(
        self,
        time_range: Optional[tuple] = None,
        namespace: str = "default",
    ) -> str:
        """Render all current L2 records as Markdown."""
        memories = self.get_all_raw(time_range, namespace)
        if not memories:
            return "# 전체 메모리\n\n메모리 없음"

        markdown = "# 전체 메모리\n\n"
        for memory in memories:
            content = memory.get("content", "")
            if isinstance(content, dict):
                content = json.dumps(content, ensure_ascii=False, indent=2)
            markdown += (
                f"## {memory.get('created_at', 'Unknown')}\n{content}\n\n---\n\n"
            )
        return markdown

    def get_all_raw(
        self,
        time_range: Optional[tuple] = None,
        namespace: str = "default",
    ) -> List[Dict]:
        """Return current, non-expired L2 records sorted newest-first."""
        self._validate_namespace(namespace)
        if self._backend == "sdk":
            memories = self._get_all_raw_sdk(namespace)
        else:
            state = self._read_state()
            ns = self._namespace_state(state, namespace)
            records = cast(Dict[str, Dict[str, Any]], ns.setdefault("records", {}))
            memories = [dict(record) for record in records.values()]

        output = []
        for memory in memories:
            if self._is_expired(memory):
                continue
            if time_range and not self._in_time_range(memory, time_range):
                continue
            output.append(memory)

        output.sort(key=lambda m: str(m.get("created_at", "")), reverse=True)
        return output

    def cleanup_expired(self, namespace: str = "default") -> int:
        """Tombstone expired L2 records."""
        deleted = 0
        if self._backend == "sdk":
            candidates = self._get_all_raw_sdk(namespace)
        else:
            state = self._read_state()
            ns = self._namespace_state(state, namespace)
            records = cast(Dict[str, Dict[str, Any]], ns.setdefault("records", {}))
            candidates = [dict(record) for record in records.values()]

        for memory in candidates:
            expires_at = memory.get("expires_at")
            if not expires_at:
                continue
            try:
                if datetime.now() > datetime.fromisoformat(str(expires_at)):
                    self._append_record("delete", memory)
                    deleted += 1
            except (ValueError, TypeError):
                continue
        return deleted

    def offload_context(
        self,
        label: str,
        content: str,
        metadata: Optional[Dict] = None,
        namespace: str = "default",
    ) -> Dict:
        """Store verbose context in the single snapshot and return a symbol."""
        self._validate_namespace(namespace)
        if not label.strip():
            raise ValueError("label은 비어있을 수 없습니다")
        if not content.strip():
            raise ValueError("content는 비어있을 수 없습니다")

        digest = hashlib.sha256(
            f"{namespace}\n{label}\n{content}".encode("utf-8")
        ).hexdigest()[:12]
        node_id = f"ctx_{digest}"
        source_ref = f"{namespace}/refs/{node_id}.jsonl"
        summary = self._summarize_offload(label, content)
        record = {
            "type": "offload",
            "node_id": node_id,
            "source_ref": source_ref,
            "label": label,
            "summary": summary,
            "content": content,
            "metadata": metadata or {},
            "created_at": datetime.now().isoformat(),
            "namespace": namespace,
        }

        if self._backend == "sdk":
            self._put_sdk_payload(
                uri=f"mv2://{namespace}/refs/{node_id}",
                title=label,
                text=summary,
                record=record,
                op="offload",
            )
        else:
            state = self._read_state()
            ns = self._namespace_state(state, namespace)
            refs = cast(Dict[str, Dict[str, Any]], ns.setdefault("refs", {}))
            refs[source_ref] = record
            self._append_python_frame(
                state=state,
                op="offload",
                namespace=namespace,
                memory_id=node_id,
                record=record,
            )
            self._write_state(state)

        mermaid_label = self._escape_mermaid_label(label)
        mermaid = f'flowchart LR\n    {node_id}["{mermaid_label}"]\n'
        return {
            "node_id": node_id,
            "source_ref": source_ref,
            "summary": summary,
            "mermaid": mermaid,
            "raw_tokens_estimate": self._estimate_tokens(content),
            "symbol_tokens_estimate": self._estimate_tokens(mermaid),
        }

    def resolve_source_ref(
        self,
        source_ref: str,
        namespace: str = "default",
    ) -> Optional[Dict]:
        """Resolve L2 or offload source references from the snapshot."""
        self._validate_namespace(namespace)
        if source_ref.startswith(f"{namespace}/L2/") and source_ref.endswith(".mv2"):
            memory_id = Path(source_ref).name.removesuffix(".mv2")
            return self.get(memory_id, namespace)

        if source_ref.startswith(f"{namespace}/refs/"):
            if self._backend == "sdk":
                return self._resolve_sdk_ref(source_ref, namespace)
            state = self._read_state()
            ns = self._namespace_state(state, namespace)
            refs = cast(Dict[str, Dict[str, Any]], ns.setdefault("refs", {}))
            record = refs.get(source_ref)
            if not record:
                return None
            return {
                "source_ref": source_ref,
                "records": [record],
                "content": str(record.get("content", "")),
            }
        return None

    def list_namespaces(self) -> List[str]:
        """List namespaces known to the snapshot."""
        if self._backend == "sdk":
            namespaces = {
                str(record.get("namespace"))
                for record in self._iter_sdk_records()
                if record.get("namespace")
            }
            namespaces.add("default")
            return sorted(namespaces)
        state = self._read_state()
        namespace_map = cast(Dict[str, Any], state.setdefault("namespaces", {}))
        namespace_map.setdefault("default", {"records": {}, "layers": {}, "refs": {}})
        return sorted(namespace_map)

    def add_relationship(
        self,
        relationship: Relationship,
        namespace: str = "default",
    ) -> bool:
        """Store relationships in the snapshot backend."""
        if self._backend == "sdk":
            record = {
                "type": "relationship",
                "namespace": namespace,
                **relationship.to_dict(),
            }
            self._put_sdk_payload(
                uri=(
                    f"mv2://{namespace}/relationships/"
                    f"{relationship.from_id}/{relationship.to_id}/"
                    f"{relationship.relation.value}/{self._next_sdk_seq()}"
                ),
                title=(
                    f"{relationship.from_id} "
                    f"{relationship.relation.value} {relationship.to_id}"
                ),
                text=(
                    f"{relationship.from_id} "
                    f"{relationship.relation.value} {relationship.to_id}"
                ),
                record=record,
                op="relationship",
            )
            return True
        self._validate_namespace(namespace)
        state = self._read_state()
        ns = self._namespace_state(state, namespace)
        relationships = cast(List[Dict[str, Any]], ns.setdefault("relationships", []))
        relationships.append(relationship.to_dict())
        self._append_python_frame(
            state=state,
            op="relationship",
            namespace=namespace,
            memory_id=relationship.from_id,
            record=relationship.to_dict(),
        )
        self._write_state(state)
        return True

    def get_relationships(
        self,
        memory_id: str,
        direction: str = "both",
        relation: Optional[RelationType] = None,
        namespace: str = "default",
    ) -> List[Relationship]:
        """Return relationships from the snapshot backend."""
        if self._backend == "sdk":
            return self._get_sdk_relationships(
                memory_id=memory_id,
                direction=direction,
                relation=relation,
                namespace=namespace,
            )
        state = self._read_state()
        ns = self._namespace_state(state, namespace)
        raw = cast(List[Dict[str, Any]], ns.setdefault("relationships", []))
        output = []
        for item in raw:
            if direction == "outgoing" and item.get("from_id") != memory_id:
                continue
            if direction == "incoming" and item.get("to_id") != memory_id:
                continue
            if direction == "both" and memory_id not in {
                item.get("from_id"),
                item.get("to_id"),
            }:
                continue
            if relation and item.get("relation") != relation.value:
                continue
            output.append(Relationship.from_dict(item))
        return output

    def delete_relationship(
        self,
        from_id: str,
        to_id: str,
        relation: Optional[RelationType] = None,
        namespace: str = "default",
    ) -> bool:
        """Delete relationships from the snapshot backend."""
        if self._backend == "sdk":
            matches = [
                rel
                for rel in self._get_sdk_relationships(
                    from_id,
                    "outgoing",
                    None,
                    namespace,
                )
                if rel.to_id == to_id and (relation is None or rel.relation == relation)
            ]
            if not matches:
                return False
            for rel in matches:
                record = {
                    "type": "relationship",
                    "namespace": namespace,
                    **rel.to_dict(),
                }
                self._put_sdk_payload(
                    uri=(
                        f"mv2://{namespace}/relationship-tombstones/"
                        f"{from_id}/{to_id}/{rel.relation.value}/{self._next_sdk_seq()}"
                    ),
                    title=f"delete {from_id} {rel.relation.value} {to_id}",
                    text=f"delete {from_id} {rel.relation.value} {to_id}",
                    record=record,
                    op="relationship_delete",
                )
            return True
        state = self._read_state()
        ns = self._namespace_state(state, namespace)
        raw = cast(List[Dict[str, Any]], ns.setdefault("relationships", []))
        original = len(raw)
        ns["relationships"] = [
            item
            for item in raw
            if not (
                item.get("from_id") == from_id
                and item.get("to_id") == to_id
                and (relation is None or item.get("relation") == relation.value)
            )
        ]
        changed = len(cast(List[Dict[str, Any]], ns["relationships"])) != original
        if changed:
            self._append_python_frame(
                state=state,
                op="relationship_delete",
                namespace=namespace,
                memory_id=from_id,
                record={"from_id": from_id, "to_id": to_id},
            )
            self._write_state(state)
        return changed

    def verify_snapshot(self, deep: bool = False) -> Dict[str, Any]:
        """Verify single-file, WAL, and index metadata for release gates."""
        info = self.snapshot_info()
        issues = []
        if not self.path.exists():
            issues.append("snapshot_missing")
        if info["sidecar_files"]:
            issues.append("sidecar_files_present")
        if self._backend == "sdk" and self._sdk_handle is not None:
            try:
                native = self._sdk_handle.verify(deep=deep)
            except Exception as exc:  # pragma: no cover - native dependent
                native = {"overall_status": "failed", "error": str(exc)}
            info["native_verify"] = native
            if native.get("overall_status") != "passed":
                issues.append("native_verify_failed")
        else:
            state = self._read_state()
            if state.get("checkpoint_seq") != len(state.get("wal", [])):
                issues.append("wal_not_checkpointed")
            for frame in state.get("frames", []):
                expected = self._checksum(frame.get("record", {}))
                if frame.get("checksum") != expected:
                    issues.append("frame_checksum_mismatch")
                    break

        return {
            **info,
            "ok": not issues,
            "issues": issues,
        }

    def snapshot_info(self) -> Dict[str, Any]:
        """Return backend and packaging evidence for docs/tests."""
        sidecars = self._sidecar_files()
        info: Dict[str, Any] = {
            "path": str(self.path),
            "backend": self._backend,
            "single_file": self.path.exists() and not sidecars,
            "sidecar_files": [str(path) for path in sidecars],
            "bm25": self.enable_bm25,
            "hnsw_requested": self.enable_hnsw,
            "hnsw": (
                "native-sdk" if self._backend == "sdk" and self.enable_hnsw else "off"
            ),
        }
        if self._backend == "sdk" and self._sdk is not None:
            try:
                sdk_info = self._sdk.info()
            except Exception:  # pragma: no cover - native dependent
                sdk_info = {}
            info["sdk"] = sdk_info
            if self._sdk_handle is not None:
                try:
                    info["stats"] = self._sdk_handle.stats()
                except Exception:  # pragma: no cover - native dependent
                    info["stats"] = {}
        else:
            state = self._read_state()
            info.update(
                {
                    "wal_entries": len(state.get("wal", [])),
                    "frame_count": len(state.get("frames", [])),
                    "checkpoint_seq": state.get("checkpoint_seq", 0),
                    "hnsw": "python-vector-graph" if self.enable_hnsw else "off",
                }
            )
        return info

    def restore_to(self, path: str) -> "MemvidStorage":
        """Copy the snapshot to ``path`` and open a new storage instance."""
        target = Path(path).expanduser()
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(self.path, target)
        return MemvidStorage(
            str(target),
            backend=self._backend_preference,
            enable_bm25=self.enable_bm25,
            enable_hnsw=self.enable_hnsw,
        )

    def _open_sdk(self) -> None:
        memvid_sdk = importlib.import_module("memvid_sdk")

        self._sdk = memvid_sdk
        if self.enable_hnsw:
            embeddings = importlib.import_module("memvid_sdk.embeddings")
            hash_embeddings = getattr(embeddings, "HashEmbeddings")
            self._sdk_embedder = hash_embeddings(dimension=32)

        if self.path.exists() and self.path.stat().st_size > 0:
            self._sdk_handle = memvid_sdk.use(
                "basic",
                str(self.path),
                mode="open",
                enable_lex=self.enable_bm25,
                enable_vec=self.enable_hnsw,
                read_only=False,
                force_writable=True,
            )
        else:
            self._sdk_handle = memvid_sdk.create(
                str(self.path),
                enable_lex=self.enable_bm25,
                enable_vec=self.enable_hnsw,
            )
        self._backend = "sdk"

    def _memory_record(
        self,
        *,
        memory_id: str,
        content: Union[str, Dict],
        metadata: Dict[str, Any],
        namespace: str,
        created_at: str,
        node_id: str,
        source_ref: str,
    ) -> Dict[str, Any]:
        record: Dict[str, Any] = {
            "id": memory_id,
            "node_id": node_id,
            "source_ref": source_ref,
            "content": content,
            "metadata": metadata,
            "created_at": created_at,
            "namespace": namespace,
        }
        if "ttl" in metadata and metadata["ttl"] is not None:
            record["expires_at"] = (
                datetime.now() + timedelta(seconds=int(metadata["ttl"]))
            ).isoformat()
        return record

    def _append_record(self, op: str, record: Dict[str, Any]) -> None:
        namespace = str(record["namespace"])
        if self._backend == "sdk":
            uri = self._record_uri(namespace, str(record["id"]))
            if op == "delete":
                uri = f"mv2://{namespace}/tombstones/{record['id']}/{self._next_sdk_seq()}"
            self._put_sdk_payload(
                uri=uri,
                title=str(record["id"]),
                text=self._content_to_text(record.get("content", "")),
                record=record,
                op=op,
            )
            return

        state = self._read_state()
        ns = self._namespace_state(state, namespace)
        records = cast(Dict[str, Dict[str, Any]], ns.setdefault("records", {}))
        if op == "delete":
            records.pop(str(record["id"]), None)
            tombstones = cast(
                Dict[str, Dict[str, Any]], ns.setdefault("tombstones", {})
            )
            tombstones[str(record["id"])] = record
        else:
            records[str(record["id"])] = record
        self._append_python_frame(
            state=state,
            op=op,
            namespace=namespace,
            memory_id=str(record["id"]),
            record=record,
        )
        self._write_state(state)

    def _put_sdk_payload(
        self,
        *,
        uri: str,
        title: str,
        text: str,
        record: Dict[str, Any],
        op: str,
    ) -> None:
        if self._sdk_handle is None:
            raise RuntimeError("memvid-sdk handle is not open")

        metadata = {
            self._SDK_RECORD_KEY: json.dumps(
                {"op": op, "record": record}, ensure_ascii=False, sort_keys=True
            ),
            self._SDK_OP_KEY: op,
            "namespace": str(record.get("namespace", "")),
        }
        timestamp = self._timestamp_seconds(record.get("created_at"))
        if self.enable_hnsw and self._sdk_embedder is not None:
            self._sdk_handle.put_many(
                [
                    {
                        "label": "memmini",
                        "title": title,
                        "text": text,
                        "uri": uri,
                        "metadata": metadata,
                        "timestamp": timestamp,
                    }
                ],
                embedder=self._sdk_embedder,
                embedding_identity={"model": "memvid-hash-32", "dimension": 32},
            )
        else:
            self._sdk_handle.put(
                title=title,
                label="memmini",
                text=text,
                uri=uri,
                metadata=metadata,
                timestamp=timestamp,
                auto_tag=False,
                extract_dates=False,
            )
        self._sdk_handle.commit()

    def _search_sdk(
        self,
        *,
        query: str,
        limit: int,
        filters: Optional[Dict],
        positive: Optional[List[str]],
        negative: Optional[List[str]],
        namespace: str,
    ) -> List[Dict]:
        if self._sdk_handle is None:
            return []
        try:
            kwargs: Dict[str, Any] = {
                "k": max(limit * 4, limit),
                "snippet_chars": 320,
                "mode": "hybrid" if self.enable_hnsw else "lex",
            }
            if self.enable_hnsw and self._sdk_embedder is not None:
                kwargs["embedder"] = self._sdk_embedder
                kwargs["query_embedding_model"] = "memvid-hash-32"
            response = self._sdk_handle.find(query, **kwargs)
        except Exception:
            return []

        output = []
        for hit in response.get("hits", []):
            uri = str(hit.get("uri", ""))
            memory_id = self._memory_id_from_uri(uri, namespace)
            if not memory_id:
                continue
            record = self.get(memory_id, namespace)
            if not record:
                continue
            if filters and not self._match_filters(record, filters):
                continue
            if not self._match_terms(record, query, positive, negative):
                continue
            output.append(
                {
                    "id": record.get("id", ""),
                    "node_id": record.get("node_id", ""),
                    "source_ref": record.get("source_ref", ""),
                    "content": record.get("content", ""),
                    "metadata": record.get("metadata", {}),
                    "similarity": float(hit.get("score", 0.0)),
                    "backend": "memvid-sdk",
                    "search_engine": "bm25+hnsw" if self.enable_hnsw else "bm25",
                }
            )
            if len(output) >= limit:
                break
        return output

    def _search_python(
        self,
        *,
        query: str,
        limit: int,
        filters: Optional[Dict],
        positive: Optional[List[str]],
        negative: Optional[List[str]],
        namespace: str,
    ) -> List[Dict]:
        memories = self.get_all_raw(namespace=namespace)
        corpus = [
            self._content_to_text(memory.get("content", "")) for memory in memories
        ]
        bm25_scores = self._bm25_scores(query, corpus)
        query_vector = self._vectorize(query)
        scored: List[Tuple[float, Dict[str, Any]]] = []

        for idx, memory in enumerate(memories):
            if filters and not self._match_filters(memory, filters):
                continue
            if not self._match_terms(memory, query, positive, negative):
                continue
            content = corpus[idx]
            if query.strip() and query.lower() not in content.lower():
                if (
                    bm25_scores[idx] <= 0
                    and self._cosine(query_vector, self._vectorize(content)) <= 0
                ):
                    continue
            vector_score = self._cosine(query_vector, self._vectorize(content))
            score = bm25_scores[idx] + (0.25 * vector_score if self.enable_hnsw else 0)
            if not query.strip():
                score = 1.0
            scored.append((score, memory))

        scored.sort(
            key=lambda item: (item[0], str(item[1].get("created_at", ""))), reverse=True
        )
        output = []
        for score, memory in scored[:limit]:
            output.append(
                {
                    "id": memory.get("id", ""),
                    "node_id": memory.get("node_id", ""),
                    "source_ref": memory.get("source_ref", ""),
                    "content": memory.get("content", ""),
                    "metadata": memory.get("metadata", {}),
                    "similarity": float(score),
                    "backend": "python",
                    "search_engine": (
                        "bm25+vector-graph" if self.enable_hnsw else "bm25"
                    ),
                }
            )
        return output

    def _get_all_raw_sdk(self, namespace: str) -> List[Dict]:
        latest: Dict[str, Tuple[int, Dict[str, Any]]] = {}
        tombstones: Dict[str, int] = {}
        for seq, item in enumerate(self._iter_sdk_records()):
            op = str(item.get("op", "save"))
            record = item.get("record", {})
            if not isinstance(record, dict):
                continue
            if record.get("namespace") != namespace:
                continue
            memory_id = str(record.get("id", ""))
            if not memory_id:
                continue
            if op == "delete":
                tombstones[memory_id] = seq
                continue
            if op in {"save", "update"}:
                if tombstones.get(memory_id, -1) > seq:
                    continue
                latest[memory_id] = (seq, record)

        return [record for _, record in latest.values()]

    def _iter_sdk_records(self) -> List[Dict[str, Any]]:
        if self._sdk_handle is None:
            return []
        try:
            timeline = self._sdk_handle.timeline(limit=1_000_000)
        except Exception:
            return []

        records = []
        for entry in timeline:
            uri = entry.get("uri")
            if not uri:
                continue
            try:
                frame = self._sdk_handle.frame(str(uri))
            except Exception:
                continue
            extra = frame.get("extra_metadata", {})
            raw = self._decode_sdk_value(extra.get(self._SDK_RECORD_KEY))
            if isinstance(raw, str):
                raw = self._decode_sdk_value(raw)
            if isinstance(raw, dict):
                records.append(raw)
        return records

    def _get_sdk_layer(self, layer: str, namespace: str) -> str:
        selected: Tuple[int, str] = (-1, "")
        for seq, item in enumerate(self._iter_sdk_records()):
            record = item.get("record", {})
            if (
                item.get("op") == "layer"
                and isinstance(record, dict)
                and record.get("namespace") == namespace
                and record.get("layer") == layer
            ):
                selected = (seq, str(record.get("content", "")))
        return selected[1]

    def _resolve_sdk_ref(self, source_ref: str, namespace: str) -> Optional[Dict]:
        for item in self._iter_sdk_records():
            record = item.get("record", {})
            if not isinstance(record, dict):
                continue
            if record.get("namespace") != namespace:
                continue
            if record.get("source_ref") == source_ref and item.get("op") == "offload":
                return {
                    "source_ref": source_ref,
                    "records": [record],
                    "content": str(record.get("content", "")),
                }
        return None

    def _get_sdk_relationships(
        self,
        memory_id: str,
        direction: str,
        relation: Optional[RelationType],
        namespace: str,
    ) -> List[Relationship]:
        keyed: Dict[Tuple[str, str, str], Dict[str, Any]] = {}
        for item in self._iter_sdk_records():
            record = item.get("record", {})
            if not isinstance(record, dict):
                continue
            if record.get("namespace") != namespace:
                continue
            if record.get("type") != "relationship":
                continue
            key = (
                str(record.get("from_id", "")),
                str(record.get("to_id", "")),
                str(record.get("relation", "")),
            )
            if not all(key):
                continue
            if item.get("op") == "relationship_delete":
                keyed.pop(key, None)
            elif item.get("op") == "relationship":
                keyed[key] = record

        output = []
        for record in keyed.values():
            if direction == "outgoing" and record.get("from_id") != memory_id:
                continue
            if direction == "incoming" and record.get("to_id") != memory_id:
                continue
            if direction == "both" and memory_id not in {
                record.get("from_id"),
                record.get("to_id"),
            }:
                continue
            if relation and record.get("relation") != relation.value:
                continue
            try:
                output.append(Relationship.from_dict(record))
            except (KeyError, ValueError):
                continue
        return output

    def _empty_state(self) -> Dict[str, Any]:
        return {
            "format": self._FORMAT,
            "format_version": self._FORMAT_VERSION,
            "created_at": datetime.now().isoformat(),
            "upstream": {
                "project": "memvid/memvid",
                "format": "mv2",
                "license": "Apache-2.0",
            },
            "indexes": {
                "lexical": "bm25",
                "vector": "python-vector-graph" if self.enable_hnsw else "off",
            },
            "checkpoint_seq": 0,
            "wal": [],
            "frames": [],
            "namespaces": {
                "default": {
                    "records": {},
                    "layers": {},
                    "refs": {},
                    "tombstones": {},
                    "relationships": [],
                }
            },
        }

    def _read_state(self) -> Dict[str, Any]:
        if not self.path.exists():
            return self._empty_state()
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                state = json.load(f)
        except (json.JSONDecodeError, OSError):
            return self._empty_state()
        if not isinstance(state, dict) or state.get("format") != self._FORMAT:
            return self._empty_state()
        return state

    def _write_state(self, state: Dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path: Optional[str] = None
        try:
            with tempfile.NamedTemporaryFile(
                "w",
                encoding="utf-8",
                dir=self.path.parent,
                prefix=f".{self.path.name}.",
                suffix=".tmp",
                delete=False,
            ) as f:
                tmp_path = f.name
                json.dump(state, f, ensure_ascii=False, indent=2, sort_keys=True)
                f.write("\n")
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_path, self.path)
            try:
                os.chmod(str(self.path), 0o600)
            except OSError:
                pass
        finally:
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass

    def _append_python_frame(
        self,
        *,
        state: Dict[str, Any],
        op: str,
        namespace: str,
        memory_id: str,
        record: Dict[str, Any],
    ) -> None:
        frames = cast(List[Dict[str, Any]], state.setdefault("frames", []))
        wal = cast(List[Dict[str, Any]], state.setdefault("wal", []))
        seq = len(wal) + 1
        checksum = self._checksum(record)
        uri = self._record_uri(namespace, memory_id)
        if op == "delete":
            uri = f"mv2://{namespace}/tombstones/{memory_id}/{seq}"
        elif op == "offload":
            uri = f"mv2://{namespace}/refs/{memory_id}"
        elif op == "layer":
            uri = f"mv2://{namespace}/layers/{memory_id}/{seq}"

        frame = {
            "frame_id": len(frames),
            "seq": seq,
            "op": op,
            "uri": uri,
            "namespace": namespace,
            "memory_id": memory_id,
            "record": record,
            "created_at": datetime.now().isoformat(),
            "checksum": checksum,
        }
        frames.append(frame)
        wal.append(
            {
                "seq": seq,
                "op": op,
                "uri": uri,
                "memory_id": memory_id,
                "namespace": namespace,
                "checksum": checksum,
                "committed": True,
            }
        )
        state["checkpoint_seq"] = seq

    def _namespace_state(self, state: Dict[str, Any], namespace: str) -> Dict[str, Any]:
        namespaces = cast(Dict[str, Dict[str, Any]], state.setdefault("namespaces", {}))
        return namespaces.setdefault(
            namespace,
            {
                "records": {},
                "layers": {},
                "refs": {},
                "tombstones": {},
                "relationships": [],
            },
        )

    def _validate_namespace(self, namespace: str) -> None:
        if not namespace or namespace in {".", ".."}:
            raise ValueError("namespace는 비어있거나 '.'/'..'일 수 없습니다")
        if "/" in namespace or "\\" in namespace or "\x00" in namespace:
            raise ValueError("namespace에는 경로 구분자를 사용할 수 없습니다")
        if Path(namespace).is_absolute():
            raise ValueError("namespace는 절대 경로일 수 없습니다")

    def _sidecar_files(self) -> List[Path]:
        forbidden_suffixes = (".wal", ".lock", ".shm")
        output = []
        for item in self.path.parent.glob(f"{self.path.name}*"):
            if item == self.path:
                continue
            if item.name.endswith(forbidden_suffixes):
                output.append(item)
        return output

    def _record_uri(self, namespace: str, memory_id: str) -> str:
        return f"mv2://{namespace}/L2/{memory_id}"

    def _memory_id_from_uri(self, uri: str, namespace: str) -> Optional[str]:
        prefix = f"mv2://{namespace}/L2/"
        if not uri.startswith(prefix):
            return None
        memory_id = uri.removeprefix(prefix).split("/", 1)[0]
        if memory_id.startswith("mem-"):
            return memory_id
        return None

    def _next_sdk_seq(self) -> int:
        if self._sdk_handle is None:
            return 0
        try:
            stats = self._sdk_handle.stats()
            return int(stats.get("seq_no", 0)) + 1
        except Exception:
            return 0

    def _decode_sdk_value(self, value: Any) -> Any:
        current = value
        for _ in range(3):
            if not isinstance(current, str):
                return current
            try:
                current = json.loads(current)
            except json.JSONDecodeError:
                return current
        return current

    def _timestamp_seconds(self, value: Any) -> int:
        if isinstance(value, int):
            return value
        if isinstance(value, float):
            return int(value)
        if isinstance(value, str):
            try:
                return int(datetime.fromisoformat(value).timestamp())
            except ValueError:
                try:
                    return int(float(value))
                except ValueError:
                    pass
        return int(datetime.now().timestamp())

    def _content_to_text(self, content: Any) -> str:
        if isinstance(content, dict):
            return json.dumps(content, ensure_ascii=False, sort_keys=True)
        return str(content)

    def _match_terms(
        self,
        memory: Dict[str, Any],
        query: str,
        positive: Optional[List[str]],
        negative: Optional[List[str]],
    ) -> bool:
        content = self._content_to_text(memory.get("content", ""))
        content_lower = content.lower()
        if query and query.lower() not in content_lower:
            query_tokens = self._tokenize(query)
            if query_tokens and not any(
                token in content_lower for token in query_tokens
            ):
                return False
        if positive and not all(term.lower() in content_lower for term in positive):
            return False
        if negative and any(term.lower() in content_lower for term in negative):
            return False
        return True

    def _match_filters(
        self, memory_data: Dict[str, Any], filters: Dict[str, Any]
    ) -> bool:
        metadata = memory_data.get("metadata", {})
        if "$and" in filters:
            return all(self._match_filters(memory_data, sub) for sub in filters["$and"])
        if "$or" in filters:
            return any(self._match_filters(memory_data, sub) for sub in filters["$or"])
        if "tags" in filters:
            memory_tags = metadata.get("tags", [])
            if not any(tag in memory_tags for tag in filters["tags"]):
                return False
        if "category" in filters and metadata.get("category") != filters["category"]:
            return False
        if "date_range" in filters:
            created_at = memory_data.get("created_at", "")
            if created_at:
                start, end = filters["date_range"]
                if not (start <= created_at <= end):
                    return False
        if "priority" in filters and metadata.get("priority") != filters["priority"]:
            return False
        return True

    def _in_time_range(self, memory_data: Dict[str, Any], time_range: tuple) -> bool:
        created_at = str(memory_data.get("created_at", ""))
        if not created_at:
            return True
        start, end = time_range
        return bool(start <= created_at <= end)

    def _is_expired(self, memory_data: Dict[str, Any]) -> bool:
        expires_at = memory_data.get("expires_at")
        if not expires_at:
            return False
        try:
            return datetime.now() > datetime.fromisoformat(str(expires_at))
        except (ValueError, TypeError):
            return False

    def _bm25_scores(self, query: str, corpus: List[str]) -> List[float]:
        query_tokens = self._tokenize(query)
        if not query_tokens:
            return [1.0 for _ in corpus]
        docs = [self._tokenize(text) for text in corpus]
        avgdl = sum(len(doc) for doc in docs) / max(len(docs), 1)
        doc_freq: Counter[str] = Counter()
        for doc in docs:
            doc_freq.update(set(doc))

        scores = []
        k1 = 1.5
        b = 0.75
        total_docs = max(len(docs), 1)
        for doc in docs:
            freqs = Counter(doc)
            doc_len = max(len(doc), 1)
            score = 0.0
            for token in query_tokens:
                if freqs[token] == 0:
                    continue
                idf = math.log(
                    1 + (total_docs - doc_freq[token] + 0.5) / (doc_freq[token] + 0.5)
                )
                denom = freqs[token] + k1 * (1 - b + b * doc_len / max(avgdl, 1))
                score += idf * (freqs[token] * (k1 + 1)) / denom
            scores.append(score)
        return scores

    def _tokenize(self, text: str) -> List[str]:
        return re.findall(r"[\w가-힣]+", text.lower())

    def _vectorize(self, text: str, dimensions: int = 32) -> List[float]:
        vector = [0.0] * dimensions
        normalized = f"  {text.lower()}  "
        grams = [normalized[i : i + 3] for i in range(max(len(normalized) - 2, 1))]
        for gram in grams:
            digest = hashlib.blake2b(gram.encode("utf-8"), digest_size=2).digest()
            idx = int.from_bytes(digest, "little") % dimensions
            vector[idx] += 1.0
        return vector

    def _cosine(self, left: List[float], right: List[float]) -> float:
        if not left or not right:
            return 0.0
        dot = sum(a * b for a, b in zip(left, right))
        left_norm = math.sqrt(sum(a * a for a in left))
        right_norm = math.sqrt(sum(b * b for b in right))
        if left_norm == 0 or right_norm == 0:
            return 0.0
        return dot / (left_norm * right_norm)

    def _checksum(self, record: Any) -> str:
        payload = json.dumps(record, ensure_ascii=False, sort_keys=True).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()

    def _summarize_offload(self, label: str, content: str) -> str:
        first_line = next(
            (line.strip() for line in content.splitlines() if line.strip()), ""
        )
        if not first_line:
            first_line = content.strip()
        if len(first_line) > 140:
            first_line = first_line[:137].rstrip() + "..."
        return f"{label}: {first_line}"

    def _escape_mermaid_label(self, label: str) -> str:
        clean = re.sub(r"\s+", " ", label.strip())
        return clean.replace('"', "'").replace("[", "(").replace("]", ")")

    def _estimate_tokens(self, text: str) -> int:
        if not text:
            return 0
        return max(1, int(len(text.split()) * 1.3))
