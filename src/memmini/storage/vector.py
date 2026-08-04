"""
MemMini Vector Storage

ChromaDB 기반 벡터 저장소.
의미 기반 검색을 제공합니다.
"""

import json
import os
import tempfile
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from memmini.core.relationship import Relationship, RelationType
from memmini.core.storage import MemoryStorage


class VectorStorage(MemoryStorage):
    """ChromaDB 벡터 저장소

    Examples:
        >>> storage = VectorStorage(
        ...     collection_name="memmini",
        ...     persist_directory="~/.memmini/chroma"
        ... )
        >>> results = storage.search("검색어", limit=5)
    """

    def __init__(
        self,
        collection_name: str = "memmini",
        persist_directory: str = "~/.memmini/chroma",
    ) -> None:
        """VectorStorage 초기화

        Args:
            collection_name: ChromaDB 컬렉션 이름
            persist_directory: 영속화 디렉토리
        """
        persist_dir = Path(persist_directory).expanduser()
        persist_dir.mkdir(parents=True, exist_ok=True)
        self.persist_dir = persist_dir

        import chromadb

        self.client = chromadb.PersistentClient(path=str(persist_dir))
        self._base_collection_name = collection_name
        self._collections: Dict[str, Any] = {}

        # 기본 namespace 컬렉션
        self.collection = self._get_collection("default")

    def _validate_namespace(self, namespace: str) -> None:
        """경로와 컬렉션 이름에 안전한 단일 namespace 세그먼트만 허용."""
        if not namespace or namespace in {".", ".."}:
            raise ValueError("namespace는 비어있거나 '.'/'..'일 수 없습니다")
        if "/" in namespace or "\\" in namespace or "\x00" in namespace:
            raise ValueError("namespace에는 경로 구분자를 사용할 수 없습니다")
        if Path(namespace).is_absolute():
            raise ValueError("namespace는 절대 경로일 수 없습니다")

    def _get_collection(self, namespace: str) -> Any:
        """네임스페이스별 컬렉션 반환"""
        self._validate_namespace(namespace)
        if namespace not in self._collections:
            name = (
                self._base_collection_name
                if namespace == "default"
                else f"{self._base_collection_name}_{namespace}"
            )
            self._collections[namespace] = self.client.get_or_create_collection(
                name=name,
                metadata={"hnsw:space": "cosine"},
            )
        return self._collections[namespace]

    def save(
        self,
        content: Union[str, Dict],
        metadata: Dict,
        namespace: str = "default",
    ) -> str:
        """벡터 저장"""
        memory_id = f"mem-{uuid.uuid4()}"
        collection = self._get_collection(namespace)

        if isinstance(content, dict):
            text = json.dumps(content, ensure_ascii=False)
        else:
            text = str(content)

        metadata = dict(metadata)
        if "ttl" in metadata and metadata["ttl"] is not None:
            ttl_seconds = int(metadata["ttl"])
            metadata["expires_at"] = (
                datetime.now() + timedelta(seconds=ttl_seconds)
            ).isoformat()

        chroma_metadata = self._flatten_metadata(metadata)

        collection.add(
            documents=[text],
            metadatas=[chroma_metadata],
            ids=[memory_id],
        )

        return memory_id

    def get(self, memory_id: str, namespace: str = "default") -> Optional[Dict]:
        """벡터 조회"""
        collection = self._get_collection(namespace)
        try:
            result = collection.get(ids=[memory_id])
            if result["ids"]:
                metadata = result["metadatas"][0] or {}
                if self._is_expired(metadata):
                    return None
                return {
                    "id": result["ids"][0],
                    "content": result["documents"][0],
                    "metadata": metadata,
                }
        except Exception:
            pass
        return None

    def update(
        self,
        memory_id: str,
        content: Union[str, Dict],
        metadata: Optional[Dict] = None,
        namespace: str = "default",
    ) -> bool:
        """벡터 수정"""
        collection = self._get_collection(namespace)
        try:
            if isinstance(content, dict):
                text = json.dumps(content, ensure_ascii=False)
            else:
                text = str(content)

            update_kwargs: Dict[str, Any] = {
                "ids": [memory_id],
                "documents": [text],
            }
            if metadata:
                update_kwargs["metadatas"] = [self._flatten_metadata(metadata)]

            collection.update(**update_kwargs)
            return True
        except Exception:
            return False

    def delete(self, memory_id: str, namespace: str = "default") -> bool:
        """벡터 삭제"""
        collection = self._get_collection(namespace)
        try:
            collection.delete(ids=[memory_id])
            return True
        except Exception:
            return False

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
        """벡터 유사도 검색"""
        collection = self._get_collection(namespace)

        where = None
        if filters or positive or negative:
            where = self._build_where_filter(filters, positive, negative)

        try:
            count = collection.count()
            if count == 0:
                return []
            results = collection.query(
                query_texts=[query],
                n_results=min(limit, count),
                where=where,
            )
        except Exception:
            return []

        if not results["ids"] or not results["ids"][0]:
            return []

        output = []
        for i in range(len(results["ids"][0])):
            distance = results["distances"][0][i] if results.get("distances") else 0
            content = results["documents"][0][i]
            metadata = results["metadatas"][0][i] if results.get("metadatas") else {}

            if self._is_expired(metadata or {}):
                continue

            # Positive/Negative 필터링 (후처리)
            if positive or negative:
                content_lower = content.lower()

                # Positive: 모든 키워드가 포함되어야 함
                if positive:
                    if not all(kw.lower() in content_lower for kw in positive):
                        continue

                # Negative: 어떤 키워드도 포함되지 않아야 함
                if negative:
                    if any(kw.lower() in content_lower for kw in negative):
                        continue

            output.append(
                {
                    "id": results["ids"][0][i],
                    "content": content,
                    "metadata": metadata or {},
                    "similarity": 1 - distance,
                }
            )

        return output

    def get_layer(
        self,
        layer: str,
        time_range: Optional[tuple] = None,
        namespace: str = "default",
    ) -> str:
        """VectorStorage는 Layer 파일 관리를 지원하지 않습니다."""
        return ""

    def save_layer(self, layer: str, content: str, namespace: str = "default") -> None:
        """VectorStorage는 Layer 파일 관리를 지원하지 않습니다."""
        pass

    def get_all(
        self,
        time_range: Optional[tuple] = None,
        namespace: str = "default",
    ) -> str:
        """전체 벡터 데이터를 Markdown으로 반환"""
        collection = self._get_collection(namespace)
        try:
            all_data = collection.get()
        except Exception:
            return "# 전체 메모리\n\n메모리 없음"

        if not all_data["ids"]:
            return "# 전체 메모리\n\n메모리 없음"

        markdown = "# 전체 메모리\n\n"
        rendered = 0
        for i in range(len(all_data["ids"])):
            content = all_data["documents"][i] if all_data.get("documents") else ""
            metadata = all_data["metadatas"][i] if all_data.get("metadatas") else {}
            if self._is_expired(metadata or {}):
                continue
            markdown += (
                f"## {metadata.get('created_at', 'Unknown')}\n" f"{content}\n\n---\n\n"
            )
            rendered += 1

        if rendered == 0:
            return "# 전체 메모리\n\n메모리 없음"
        return markdown

    def get_all_raw(
        self,
        time_range: Optional[tuple] = None,
        namespace: str = "default",
    ) -> List[Dict]:
        """전체 벡터 데이터를 원시 딕셔너리 리스트로 반환."""
        collection = self._get_collection(namespace)
        try:
            all_data = collection.get()
        except Exception:
            return []

        memories = []
        for i, memory_id in enumerate(all_data.get("ids", [])):
            metadata = all_data["metadatas"][i] if all_data.get("metadatas") else {}
            if self._is_expired(metadata or {}):
                continue

            created_at = (metadata or {}).get("created_at", "")
            if time_range and created_at:
                start, end = time_range
                if not (start <= created_at <= end):
                    continue

            memories.append(
                {
                    "id": memory_id,
                    "content": (
                        all_data["documents"][i] if all_data.get("documents") else ""
                    ),
                    "metadata": metadata or {},
                    "created_at": created_at,
                    "namespace": namespace,
                }
            )

        memories.sort(key=lambda item: item.get("created_at", ""), reverse=True)
        return memories

    def cleanup_expired(self, namespace: str = "default") -> int:
        """만료된 벡터 메모리 삭제."""
        collection = self._get_collection(namespace)
        try:
            all_data = collection.get()
        except Exception:
            return 0

        expired_ids = []
        for i, memory_id in enumerate(all_data.get("ids", [])):
            metadata = all_data["metadatas"][i] if all_data.get("metadatas") else {}
            if self._is_expired(metadata or {}):
                expired_ids.append(memory_id)

        if expired_ids:
            collection.delete(ids=expired_ids)

        return len(expired_ids)

    def _flatten_metadata(self, metadata: Dict) -> Dict:
        """ChromaDB에 저장 가능한 형태로 메타데이터 변환"""
        flat: Dict[str, Any] = {}
        for key, value in metadata.items():
            if isinstance(value, (str, int, float, bool)):
                flat[key] = value
            elif isinstance(value, list):
                flat[key] = json.dumps(value, ensure_ascii=False)
            elif isinstance(value, dict):
                flat[key] = json.dumps(value, ensure_ascii=False)
            elif value is None:
                flat[key] = ""
            else:
                flat[key] = str(value)

        # ChromaDB는 빈 metadata를 거부하므로 기본값 추가
        if not flat:
            flat["_default"] = "true"

        return flat

    def _build_where_filter(
        self,
        filters: Optional[Dict] = None,
        positive: Optional[List[str]] = None,
        negative: Optional[List[str]] = None,
    ) -> Optional[Dict]:
        """ChromaDB where 필터 구성 (positive/negative 지원)"""
        conditions: List[Dict[str, Any]] = []

        # 기존 filters 처리
        if filters:
            for key, value in filters.items():
                if isinstance(value, list):
                    for v in value:
                        conditions.append({key: {"$contains": str(v)}})
                else:
                    conditions.append({key: str(value)})

        # Positive keywords (content에 포함되어야 함)
        if positive:
            # ChromaDB는 document contains where 필터가 제한적입니다.
            # 키워드 필터는 search() 후처리에서 적용합니다.
            pass

        # Negative keywords (content에 없어야 함)
        if negative:
            # 키워드 필터는 search() 후처리에서 적용합니다.
            pass

        if len(conditions) == 1:
            return conditions[0]
        elif len(conditions) > 1:
            return {"$and": conditions}

        return None

    def _is_expired(self, metadata: Dict) -> bool:
        """metadata의 expires_at 기준으로 만료 여부 확인."""
        expires_at = metadata.get("expires_at")
        if not expires_at:
            return False

        try:
            return datetime.now() > datetime.fromisoformat(str(expires_at))
        except (ValueError, TypeError):
            return False

    def _read_relationships(self, rel_file: Path) -> List[Dict]:
        try:
            with open(rel_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, list) else []
        except (json.JSONDecodeError, OSError):
            return []

    def _write_relationships_atomic(self, rel_file: Path, relationships: List) -> None:
        rel_file.parent.mkdir(parents=True, exist_ok=True)
        tmp_path: Optional[str] = None
        try:
            with tempfile.NamedTemporaryFile(
                "w",
                encoding="utf-8",
                dir=rel_file.parent,
                prefix=f".{rel_file.name}.",
                suffix=".tmp",
                delete=False,
            ) as f:
                tmp_path = f.name
                json.dump(relationships, f, ensure_ascii=False, indent=2)
                f.write("\n")
                f.flush()
                os.fsync(f.fileno())

            os.replace(tmp_path, rel_file)
            try:
                os.chmod(str(rel_file), 0o600)
            except OSError:
                pass
        finally:
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass

    def add_relationship(
        self,
        relationship: Relationship,
        namespace: str = "default",
    ) -> bool:
        """관계 추가 (VectorStorage는 FileStorage와 동일하게 JSON 파일 사용)"""
        rel_file = self._relationship_file(namespace)

        relationships = self._read_relationships(rel_file)

        relationships.append(relationship.to_dict())

        self._write_relationships_atomic(rel_file, relationships)

        return True

    def get_relationships(
        self,
        memory_id: str,
        direction: str = "both",
        relation: Optional[RelationType] = None,
        namespace: str = "default",
    ) -> List[Relationship]:
        """관계 조회"""
        rel_file = self._relationship_file(namespace)

        if not rel_file.exists():
            return []

        all_rels = self._read_relationships(rel_file)

        results = []
        for rel_data in all_rels:
            if direction == "outgoing" and rel_data["from_id"] != memory_id:
                continue
            if direction == "incoming" and rel_data["to_id"] != memory_id:
                continue
            if direction == "both":
                if rel_data["from_id"] != memory_id and rel_data["to_id"] != memory_id:
                    continue

            if relation and rel_data["relation"] != relation.value:
                continue

            results.append(Relationship.from_dict(rel_data))

        return results

    def delete_relationship(
        self,
        from_id: str,
        to_id: str,
        relation: Optional[RelationType] = None,
        namespace: str = "default",
    ) -> bool:
        """관계 삭제"""
        rel_file = self._relationship_file(namespace)

        if not rel_file.exists():
            return False

        all_rels = self._read_relationships(rel_file)

        new_rels = []
        deleted = False
        for rel_data in all_rels:
            if rel_data["from_id"] == from_id and rel_data["to_id"] == to_id:
                if relation is None or rel_data["relation"] == relation.value:
                    deleted = True
                    continue
            new_rels.append(rel_data)

        if deleted:
            self._write_relationships_atomic(rel_file, new_rels)

        return deleted

    def _relationship_file(self, namespace: str) -> Path:
        self._validate_namespace(namespace)
        return self.persist_dir / f"relationships_{namespace}.json"
