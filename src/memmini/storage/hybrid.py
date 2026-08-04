"""
MemMini Hybrid Storage

파일 + 벡터 하이브리드 저장소.
파일 저장소에서 원본 데이터를 관리하고, 벡터 저장소에서 검색을 수행합니다.
"""

import json
from typing import Dict, List, Optional, Union

from memmini.core.relationship import Relationship, RelationType
from memmini.core.storage import MemoryStorage
from memmini.storage.file import FileStorage
from memmini.storage.vector import VectorStorage


class HybridStorage(MemoryStorage):
    """파일 + 벡터 하이브리드 저장소

    - 파일: 원본 저장, 메타데이터 관리, L0/L1 레이어
    - 벡터: 의미 기반 검색

    Examples:
        >>> file_storage = FileStorage()
        >>> vector_storage = VectorStorage()
        >>> storage = HybridStorage(file_storage, vector_storage)
        >>> storage.save("내용", {"tags": ["test"]})
    """

    def __init__(
        self,
        file_storage: FileStorage,
        vector_storage: VectorStorage,
    ):
        self.file_storage = file_storage
        self.vector_storage = vector_storage

    def save(
        self,
        content: Union[str, Dict],
        metadata: Dict,
        namespace: str = "default",
    ) -> str:
        """파일과 벡터에 동시 저장"""
        memory_id = self.file_storage.save(content, metadata, namespace)

        try:
            if isinstance(content, dict):
                text = json.dumps(content, ensure_ascii=False)
            else:
                text = str(content)

            chroma_metadata = self.vector_storage._flatten_metadata(metadata)
            collection = self.vector_storage._get_collection(namespace)
            collection.add(
                documents=[text],
                metadatas=[chroma_metadata],
                ids=[memory_id],
            )
        except Exception:
            pass

        return memory_id

    def get(self, memory_id: str, namespace: str = "default") -> Optional[Dict]:
        """파일 저장소에서 조회 (원본 데이터)"""
        return self.file_storage.get(memory_id, namespace)

    def update(
        self,
        memory_id: str,
        content: Union[str, Dict],
        metadata: Optional[Dict] = None,
        namespace: str = "default",
    ) -> bool:
        """파일 + 벡터 동시 수정"""
        result = self.file_storage.update(memory_id, content, metadata, namespace)
        if result:
            try:
                self.vector_storage.update(memory_id, content, metadata, namespace)
            except Exception:
                pass
        return result

    def delete(self, memory_id: str, namespace: str = "default") -> bool:
        """파일 + 벡터 동시 삭제"""
        result = self.file_storage.delete(memory_id, namespace)
        if result:
            try:
                self.vector_storage.delete(memory_id, namespace)
            except Exception:
                pass
        return result

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
        """벡터 검색 + 파일 메타데이터 결합"""
        vector_results = self.vector_storage.search(
            query, layer, limit * 2, filters, positive, negative, namespace
        )

        enriched = []
        for result in vector_results[:limit]:
            memory_id = result["id"]
            full_data = self.file_storage.get(memory_id, namespace)
            if full_data:
                enriched.append(
                    {
                        **full_data,
                        "similarity": result.get("similarity", 0.0),
                    }
                )
            else:
                enriched.append(result)

        return enriched

    def get_layer(
        self,
        layer: str,
        time_range: Optional[tuple] = None,
        namespace: str = "default",
    ) -> str:
        """파일 저장소의 Layer 파일 사용"""
        return self.file_storage.get_layer(layer, time_range, namespace)

    def save_layer(self, layer: str, content: str, namespace: str = "default") -> None:
        """파일 저장소의 Layer 파일 저장"""
        self.file_storage.save_layer(layer, content, namespace)

    def get_all(
        self,
        time_range: Optional[tuple] = None,
        namespace: str = "default",
    ) -> str:
        """파일 저장소의 전체 메모리"""
        return self.file_storage.get_all(time_range, namespace)

    def get_all_raw(
        self,
        time_range: Optional[tuple] = None,
        namespace: str = "default",
    ) -> List[Dict]:
        """파일 저장소의 전체 메모리 (원시)"""
        return self.file_storage.get_all_raw(time_range, namespace)

    def cleanup_expired(self, namespace: str = "default") -> int:
        """만료된 메모리 정리 (파일 + 벡터)"""
        # 먼저 만료 ID 수집
        self.file_storage._ensure_namespace(namespace)
        expired_ids = []
        l2_dir = self.file_storage._ns_path(namespace) / "L2"
        for file_path in l2_dir.glob("*.json"):
            import json as _json

            with open(file_path, "r", encoding="utf-8") as f:
                data = _json.load(f)
            if self.file_storage._is_expired(data):
                expired_ids.append(data.get("id"))

        # 파일 삭제
        deleted = self.file_storage.cleanup_expired(namespace)

        # 벡터 삭제
        for mem_id in expired_ids:
            if mem_id:
                try:
                    self.vector_storage.delete(mem_id, namespace)
                except Exception:
                    pass

        return deleted

    def list_namespaces(self) -> List[str]:
        """파일 저장소의 네임스페이스 목록"""
        return self.file_storage.list_namespaces()

    def add_relationship(
        self,
        relationship: Relationship,
        namespace: str = "default",
    ) -> bool:
        """관계 추가 (FileStorage 사용)"""
        return self.file_storage.add_relationship(relationship, namespace)

    def get_relationships(
        self,
        memory_id: str,
        direction: str = "both",
        relation: Optional[RelationType] = None,
        namespace: str = "default",
    ) -> List[Relationship]:
        """관계 조회 (FileStorage 사용)"""
        return self.file_storage.get_relationships(
            memory_id, direction, relation, namespace
        )

    def delete_relationship(
        self,
        from_id: str,
        to_id: str,
        relation: Optional[RelationType] = None,
        namespace: str = "default",
    ) -> bool:
        """관계 삭제 (FileStorage 사용)"""
        return self.file_storage.delete_relationship(
            from_id, to_id, relation, namespace
        )
