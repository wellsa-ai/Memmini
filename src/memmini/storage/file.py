"""
MemMini File Storage

파일 시스템 기반 저장소.
~/.memmini/ 디렉토리에 JSON 파일로 메모리를 저장합니다.
"""

import hashlib
import json
import os
import re
import tempfile
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Union, cast

from memmini.core.relationship import Relationship, RelationType
from memmini.core.storage import MemoryStorage


class FileStorage(MemoryStorage):
    """파일 시스템 기반 저장소

    구조:
        base_path/
        ├── default/            # namespace
        │   ├── L0.md
        │   ├── L1.md
        │   └── L2/
        │       ├── mem-xxx.json
        │       └── mem-yyy.json
        └── agent-1/            # 다른 namespace
            ├── L0.md
            └── ...

    Examples:
        >>> storage = FileStorage(base_path="~/.memmini")
        >>> memory_id = storage.save("내용", {"tags": ["test"]})
        >>> data = storage.get(memory_id)
    """

    def __init__(self, base_path: str = "~/.memmini"):
        """FileStorage 초기화

        Args:
            base_path: 메모리 저장 경로 (기본 ~/.memmini)
        """
        self.path = Path(base_path).expanduser()
        self.path.mkdir(parents=True, exist_ok=True)

        # 디렉토리 권한 설정 (소유자만 접근)
        try:
            os.chmod(str(self.path), 0o700)
        except OSError:
            pass  # Windows 등에서는 무시

        # 기본 namespace 초기화 (하위 호환)
        self._ensure_namespace("default")

        # 하위 호환 속성 (기본 namespace 기준)
        self.l0_file = self._ns_path("default") / "L0.md"
        self.l1_file = self._ns_path("default") / "L1.md"
        self.l2_dir = self._ns_path("default") / "L2"

    def _ns_path(self, namespace: str) -> Path:
        """네임스페이스 경로 반환"""
        self._validate_namespace(namespace)
        return self.path / namespace

    def _validate_namespace(self, namespace: str) -> None:
        """경로 traversal을 막기 위해 namespace를 단일 경로 세그먼트로 제한."""
        if not namespace or namespace in {".", ".."}:
            raise ValueError("namespace는 비어있거나 '.'/'..'일 수 없습니다")
        if "/" in namespace or "\\" in namespace or "\x00" in namespace:
            raise ValueError("namespace에는 경로 구분자를 사용할 수 없습니다")
        if Path(namespace).is_absolute():
            raise ValueError("namespace는 절대 경로일 수 없습니다")

    def _ensure_namespace(self, namespace: str) -> None:
        """네임스페이스 디렉토리 생성"""
        ns_path = self._ns_path(namespace)
        ns_path.mkdir(parents=True, exist_ok=True)
        (ns_path / "L2").mkdir(exist_ok=True)

    def _read_json(self, file_path: Path) -> Optional[Union[Dict[str, Any], List[Any]]]:
        """JSON 파일을 읽고, 손상된 파일은 호출자가 건너뛸 수 있게 None 반환."""
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                return cast(Union[Dict[str, Any], List[Any]], json.load(f))
        except (json.JSONDecodeError, OSError):
            return None

    def _write_json_atomic(self, file_path: Path, data: Union[Dict, List]) -> None:
        """같은 디렉토리에 임시 파일을 쓴 뒤 rename하여 부분 쓰기를 방지."""
        file_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path: Optional[str] = None
        try:
            with tempfile.NamedTemporaryFile(
                "w",
                encoding="utf-8",
                dir=file_path.parent,
                prefix=f".{file_path.name}.",
                suffix=".tmp",
                delete=False,
            ) as f:
                tmp_path = f.name
                json.dump(data, f, ensure_ascii=False, indent=2)
                f.write("\n")
                f.flush()
                os.fsync(f.fileno())

            os.replace(tmp_path, file_path)
            try:
                os.chmod(str(file_path), 0o600)
            except OSError:
                pass
        finally:
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass

    def _write_text_atomic(self, file_path: Path, content: str) -> None:
        """텍스트 레이어 파일을 원자적으로 저장."""
        file_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path: Optional[str] = None
        try:
            with tempfile.NamedTemporaryFile(
                "w",
                encoding="utf-8",
                dir=file_path.parent,
                prefix=f".{file_path.name}.",
                suffix=".tmp",
                delete=False,
            ) as f:
                tmp_path = f.name
                f.write(content)
                f.flush()
                os.fsync(f.fileno())

            os.replace(tmp_path, file_path)
            try:
                os.chmod(str(file_path), 0o600)
            except OSError:
                pass
        finally:
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass

    def save(
        self,
        content: Union[str, Dict],
        metadata: Dict,
        namespace: str = "default",
    ) -> str:
        """메모리 저장 (JSON 파일)"""
        self._ensure_namespace(namespace)
        memory_id = f"mem-{uuid.uuid4()}"
        metadata = dict(metadata)
        created_at = datetime.now().isoformat()
        default_node_id = f"node_{memory_id.removeprefix('mem-')}"
        default_source_ref = f"{namespace}/L2/{memory_id}.json"
        node_id = str(metadata.get("node_id") or default_node_id)
        source_ref = str(metadata.get("source_ref") or default_source_ref)
        metadata.setdefault("node_id", node_id)
        metadata.setdefault("source_ref", source_ref)

        memory_data = {
            "id": memory_id,
            "node_id": node_id,
            "source_ref": source_ref,
            "content": content,
            "metadata": metadata,
            "created_at": created_at,
            "namespace": namespace,
        }

        # TTL 처리: metadata에 ttl이 있으면 expires_at 설정
        if "ttl" in metadata and metadata["ttl"] is not None:
            ttl_seconds = metadata["ttl"]
            from datetime import timedelta

            expires_at = datetime.now() + timedelta(seconds=ttl_seconds)
            memory_data["expires_at"] = expires_at.isoformat()

        file_path = self._ns_path(namespace) / "L2" / f"{memory_id}.json"
        self._write_json_atomic(file_path, memory_data)

        return memory_id

    def get(self, memory_id: str, namespace: str = "default") -> Optional[Dict]:
        """메모리 조회"""
        file_path = self._ns_path(namespace) / "L2" / f"{memory_id}.json"
        if not file_path.exists():
            return None

        raw_data = self._read_json(file_path)
        if not isinstance(raw_data, dict):
            return None
        data = cast(Dict[str, Any], raw_data)

        # 만료 확인
        if self._is_expired(data):
            return None

        return data

    def update(
        self,
        memory_id: str,
        content: Union[str, Dict],
        metadata: Optional[Dict] = None,
        namespace: str = "default",
    ) -> bool:
        """메모리 수정"""
        file_path = self._ns_path(namespace) / "L2" / f"{memory_id}.json"
        if not file_path.exists():
            return False

        raw_data = self._read_json(file_path)
        if not isinstance(raw_data, dict):
            return False
        memory_data = raw_data

        memory_data["content"] = content
        if metadata is not None:
            memory_data["metadata"] = metadata
        memory_data["updated_at"] = datetime.now().isoformat()

        self._write_json_atomic(file_path, memory_data)

        return True

    def delete(self, memory_id: str, namespace: str = "default") -> bool:
        """메모리 삭제"""
        file_path = self._ns_path(namespace) / "L2" / f"{memory_id}.json"
        if not file_path.exists():
            return False

        file_path.unlink()
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
        """키워드 기반 검색"""
        self._ensure_namespace(namespace)
        results = []
        query_lower = query.lower()

        l2_dir = self._ns_path(namespace) / "L2"
        for file_path in l2_dir.glob("*.json"):
            raw_data = self._read_json(file_path)
            if not isinstance(raw_data, dict):
                continue
            memory_data = raw_data

            # 만료 확인
            if self._is_expired(memory_data):
                continue

            # 내용 검색
            content = memory_data.get("content", "")
            if isinstance(content, dict):
                content_str = json.dumps(content, ensure_ascii=False)
            else:
                content_str = str(content)

            if query_lower in content_str.lower():
                content_lower = content_str.lower()

                # Positive 필터: 모든 키워드 포함 확인
                if positive:
                    if not all(kw.lower() in content_lower for kw in positive):
                        continue

                # Negative 필터: 어떤 키워드도 없어야 함
                if negative:
                    if any(kw.lower() in content_lower for kw in negative):
                        continue

                # 메타데이터 필터 적용
                if filters and not self._match_filters(memory_data, filters):
                    continue

                results.append(
                    {
                        "id": memory_data.get("id", ""),
                        "node_id": memory_data.get("node_id")
                        or memory_data.get("metadata", {}).get("node_id", ""),
                        "source_ref": memory_data.get(
                            "source_ref",
                            memory_data.get("metadata", {}).get("source_ref", ""),
                        ),
                        "content": memory_data.get("content", ""),
                        "metadata": memory_data.get("metadata", {}),
                        "similarity": 1.0,
                    }
                )

        return results[:limit]

    def get_layer(
        self,
        layer: str,
        time_range: Optional[tuple] = None,
        namespace: str = "default",
    ) -> str:
        """계층별 파일 읽기 (L0/L1)"""
        self._ensure_namespace(namespace)
        if layer == "L0":
            file_path = self._ns_path(namespace) / "L0.md"
        elif layer == "L1":
            file_path = self._ns_path(namespace) / "L1.md"
        else:
            raise ValueError("get_layer는 L0/L1만 지원 (L2는 get_all 사용)")

        if not file_path.exists():
            return ""

        with open(file_path, "r", encoding="utf-8") as f:
            return f.read()

    def save_layer(self, layer: str, content: str, namespace: str = "default") -> None:
        """계층별 파일 저장 (L0/L1)"""
        self._ensure_namespace(namespace)
        if layer == "L0":
            file_path = self._ns_path(namespace) / "L0.md"
        elif layer == "L1":
            file_path = self._ns_path(namespace) / "L1.md"
        else:
            raise ValueError("save_layer는 L0/L1만 지원")

        self._write_text_atomic(file_path, content)

    def get_all(
        self,
        time_range: Optional[tuple] = None,
        namespace: str = "default",
    ) -> str:
        """전체 메모리 로드 (L2, Markdown 형식)"""
        memories = self.get_all_raw(time_range, namespace)

        if not memories:
            return "# 전체 메모리\n\n메모리 없음"

        markdown = "# 전체 메모리\n\n"
        for mem in memories:
            timestamp = mem.get("created_at", "Unknown")
            content = mem.get("content", "")
            if isinstance(content, dict):
                content = json.dumps(content, ensure_ascii=False, indent=2)
            markdown += f"## {timestamp}\n{content}\n\n---\n\n"

        return markdown

    def get_all_raw(
        self,
        time_range: Optional[tuple] = None,
        namespace: str = "default",
    ) -> List[Dict]:
        """전체 메모리를 원시 딕셔너리 리스트로 반환"""
        self._ensure_namespace(namespace)
        memories = []

        l2_dir = self._ns_path(namespace) / "L2"
        for file_path in l2_dir.glob("*.json"):
            raw_data = self._read_json(file_path)
            if not isinstance(raw_data, dict):
                continue
            memory_data = raw_data

            # 만료 확인
            if self._is_expired(memory_data):
                continue

            # 시간 범위 필터
            if time_range and not self._in_time_range(memory_data, time_range):
                continue

            memories.append(memory_data)

        # 시간순 정렬 (최신 우선)
        memories.sort(
            key=lambda m: m.get("created_at", ""),
            reverse=True,
        )

        return memories

    def cleanup_expired(self, namespace: str = "default") -> int:
        """만료된 메모리 파일 삭제"""
        self._ensure_namespace(namespace)
        deleted = 0

        l2_dir = self._ns_path(namespace) / "L2"
        for file_path in l2_dir.glob("*.json"):
            raw_data = self._read_json(file_path)
            if not isinstance(raw_data, dict):
                continue
            memory_data = raw_data

            if self._is_expired(memory_data):
                file_path.unlink()
                deleted += 1

        return deleted

    def list_namespaces(self) -> List[str]:
        """사용 가능한 네임스페이스 목록 반환"""
        namespaces = []
        for item in self.path.iterdir():
            if item.is_dir() and (item / "L2").exists():
                namespaces.append(item.name)
        return sorted(namespaces)

    def offload_context(
        self,
        label: str,
        content: str,
        metadata: Optional[Dict] = None,
        namespace: str = "default",
    ) -> Dict:
        """긴 단기 컨텍스트를 JSONL로 내리고 Mermaid 참조만 반환."""
        if not label.strip():
            raise ValueError("label은 비어있을 수 없습니다")
        if not content.strip():
            raise ValueError("content는 비어있을 수 없습니다")

        self._ensure_namespace(namespace)
        digest = hashlib.sha256(
            f"{namespace}\n{label}\n{content}".encode("utf-8")
        ).hexdigest()[:12]
        node_id = f"ctx_{digest}"
        source_ref = f"{namespace}/refs/{node_id}.jsonl"
        created_at = datetime.now().isoformat()
        summary = self._summarize_offload(label, content)
        record = {
            "type": "offload",
            "node_id": node_id,
            "source_ref": source_ref,
            "label": label,
            "summary": summary,
            "content": content,
            "metadata": metadata or {},
            "created_at": created_at,
            "namespace": namespace,
        }

        ref_file = self._ns_path(namespace) / "refs" / f"{node_id}.jsonl"
        jsonl = json.dumps(record, ensure_ascii=False) + "\n"
        self._write_text_atomic(ref_file, jsonl)

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
        """source_ref로 원문 JSON 또는 offload JSONL을 조회합니다."""
        self._ensure_namespace(namespace)
        if source_ref.startswith(f"{namespace}/L2/") and source_ref.endswith(".json"):
            memory_id = Path(source_ref).name.removesuffix(".json")
            if "/" in memory_id or "\\" in memory_id:
                return None
            return self.get(memory_id, namespace)

        if source_ref.startswith(f"{namespace}/refs/") and source_ref.endswith(
            ".jsonl"
        ):
            ref_name = Path(source_ref).name
            if "/" in ref_name or "\\" in ref_name:
                return None
            ref_file = self._ns_path(namespace) / "refs" / ref_name
            if not ref_file.exists():
                return None
            try:
                records = [
                    json.loads(line)
                    for line in ref_file.read_text(encoding="utf-8").splitlines()
                    if line.strip()
                ]
            except (json.JSONDecodeError, OSError):
                return None
            return {
                "source_ref": source_ref,
                "records": records,
                "content": "\n".join(str(r.get("content", "")) for r in records),
            }

        return None

    def _summarize_offload(self, label: str, content: str) -> str:
        first_line = next(
            (line.strip() for line in content.splitlines() if line.strip()),
            "",
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

    def _match_filters(self, memory_data: Dict, filters: Dict) -> bool:
        """필터 조건 충족 여부 확인

        Supports:
            - tags: 태그 리스트 비교 (OR)
            - category: 카테고리 일치
            - date_range: (start, end) 날짜 범위
            - $and: 모든 조건 충족
            - $or: 하나 이상 조건 충족
        """
        metadata = memory_data.get("metadata", {})

        # $and 복합 필터
        if "$and" in filters:
            return all(self._match_filters(memory_data, sub) for sub in filters["$and"])

        # $or 복합 필터
        if "$or" in filters:
            return any(self._match_filters(memory_data, sub) for sub in filters["$or"])

        # 태그 필터
        if "tags" in filters:
            memory_tags = metadata.get("tags", [])
            if not any(t in memory_tags for t in filters["tags"]):
                return False

        # 카테고리 필터
        if "category" in filters:
            if metadata.get("category") != filters["category"]:
                return False

        # 날짜 범위 필터
        if "date_range" in filters:
            created_at = memory_data.get("created_at", "")
            if created_at:
                start, end = filters["date_range"]
                if not (start <= created_at <= end):
                    return False

        # priority 필터
        if "priority" in filters:
            if metadata.get("priority") != filters["priority"]:
                return False

        return True

    def _in_time_range(self, memory_data: Dict, time_range: tuple) -> bool:
        """시간 범위 내인지 확인"""
        created_at = memory_data.get("created_at", "")
        if not created_at:
            return True

        start, end = time_range
        return bool(start <= created_at <= end)

    def _is_expired(self, memory_data: Dict) -> bool:
        """메모리 만료 여부 확인"""
        expires_at = memory_data.get("expires_at")
        if not expires_at:
            return False

        try:
            expiry = datetime.fromisoformat(expires_at)
            return datetime.now() > expiry
        except (ValueError, TypeError):
            return False

    def add_relationship(
        self,
        relationship: Relationship,
        namespace: str = "default",
    ) -> bool:
        """관계 추가 (relationships.json 파일에 저장)"""
        self._ensure_namespace(namespace)
        rel_file = self._ns_path(namespace) / "relationships.json"

        # 기존 관계 로드
        relationships = []
        if rel_file.exists():
            raw_relationships = self._read_json(rel_file)
            if isinstance(raw_relationships, list):
                relationships = raw_relationships

        # 새 관계 추가
        relationships.append(relationship.to_dict())

        # 저장
        self._write_json_atomic(rel_file, relationships)

        return True

    def get_relationships(
        self,
        memory_id: str,
        direction: str = "both",
        relation: Optional[RelationType] = None,
        namespace: str = "default",
    ) -> List[Relationship]:
        """관계 조회"""
        self._ensure_namespace(namespace)
        rel_file = self._ns_path(namespace) / "relationships.json"

        if not rel_file.exists():
            return []

        raw_relationships = self._read_json(rel_file)
        if not isinstance(raw_relationships, list):
            return []
        all_rels = raw_relationships

        results = []
        for rel_data in all_rels:
            # Direction 필터
            if direction == "outgoing" and rel_data["from_id"] != memory_id:
                continue
            if direction == "incoming" and rel_data["to_id"] != memory_id:
                continue
            if direction == "both":
                if rel_data["from_id"] != memory_id and rel_data["to_id"] != memory_id:
                    continue

            # Relation 필터
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
        self._ensure_namespace(namespace)
        rel_file = self._ns_path(namespace) / "relationships.json"

        if not rel_file.exists():
            return False

        raw_relationships = self._read_json(rel_file)
        if not isinstance(raw_relationships, list):
            return False
        all_rels = raw_relationships

        # 필터링
        new_rels = []
        deleted = False
        for rel_data in all_rels:
            if rel_data["from_id"] == from_id and rel_data["to_id"] == to_id:
                if relation is None or rel_data["relation"] == relation.value:
                    deleted = True
                    continue  # 삭제
            new_rels.append(rel_data)

        if deleted:
            self._write_json_atomic(rel_file, new_rels)

        return deleted
