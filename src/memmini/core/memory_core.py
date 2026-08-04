"""
MemMini Memory Core

핵심 메모리 엔진 — L0/L1/L2 계층형 메모리 관리.
"""

import time
from datetime import datetime
from typing import Dict, List, Optional, Union, cast

from memmini.core.layer_generator import LayerGenerator
from memmini.core.relationship import Relationship, RelationType
from memmini.core.storage import MemoryStorage
from memmini.logic.query_analyzer import QueryAnalyzer


class MemoryCore:
    """MemMini 핵심 메모리 엔진

    L0/L1/L2 계층형 메모리 관리 시스템.
    토큰 60-80% 절약, 빠른 검색, 자동 요약 기능 제공.

    Examples:
        >>> from memmini import MemoryCore
        >>> from memmini.storage.file import FileStorage
        >>> memory = MemoryCore(storage=FileStorage())
        >>> memory_id = memory.add("사용자는 Python 개발자")
        >>> l0 = memory.retrieve(layer="L0")  # ~100 tokens

    Attributes:
        storage: 저장소 백엔드
        layers: L0/L1/L2 생성기
        auto_update: 자동 레이어 업데이트 여부
        cache_ttl: 캐시 유효 시간 (초)
        namespace: 현재 네임스페이스
    """

    def __init__(
        self,
        storage: MemoryStorage,
        layer_generator: Optional[LayerGenerator] = None,
        auto_layer_update: bool = True,
        cache_ttl: int = 3600,
        namespace: str = "default",
        auto_layer_interval: int = 0,
    ):
        """MemoryCore 초기화

        Args:
            storage: 저장소 백엔드 (FileStorage, VectorStorage 등)
            layer_generator: L0/L1/L2 생성기 (None이면 기본 생성)
            auto_layer_update: 메모리 추가 시 자동으로 L0/L1 업데이트 여부
            cache_ttl: 캐시 유효 시간 (초), 0이면 캐싱 비활성화
            namespace: 네임스페이스 (사용자/에이전트별 분리)
            auto_layer_interval: N개 추가마다 자동 update_layers() (0이면 비활성화)
        """
        self.storage = storage
        self.layers = layer_generator or LayerGenerator()
        self.query_analyzer = QueryAnalyzer()
        self.auto_update = auto_layer_update
        self.cache_ttl = cache_ttl
        self.namespace = namespace
        self.auto_layer_interval = auto_layer_interval
        self._cache: Dict[str, tuple[str, float]] = {}
        self._stats: Dict[str, int] = {
            "total_memories": 0,
            "cache_hits": 0,
            "cache_misses": 0,
        }
        self._add_count = 0  # auto_layer_interval 카운터

    @classmethod
    def from_path(
        cls,
        path: str = "~/.memmini",
        *,
        layer_generator: Optional[LayerGenerator] = None,
        auto_layer_update: bool = True,
        cache_ttl: int = 3600,
        namespace: str = "default",
        auto_layer_interval: int = 0,
    ) -> "MemoryCore":
        """파일 저장소 기반 MemoryCore를 짧게 생성합니다.

        Examples:
            >>> memory = MemoryCore.from_path("./memory", auto_layer_update=False)
            >>> memory.add("Project note")
        """
        from memmini.storage.file import FileStorage

        return cls(
            storage=FileStorage(base_path=path),
            layer_generator=layer_generator,
            auto_layer_update=auto_layer_update,
            cache_ttl=cache_ttl,
            namespace=namespace,
            auto_layer_interval=auto_layer_interval,
        )

    def add(
        self,
        content: Union[str, Dict],
        metadata: Optional[Dict] = None,
        layer: str = "L2",
        ttl: Optional[int] = None,
    ) -> str:
        """메모리 추가

        새로운 메모리를 저장하고 UUID를 반환합니다.

        Args:
            content: 메모리 내용 (문자열 또는 딕셔너리)
            metadata: 메타데이터 (태그, 카테고리, 우선순위 등)
            layer: 저장할 계층 (기본 "L2")
            ttl: 메모리 유효 시간 (초), None이면 영구 보존

        Returns:
            memory_id: 생성된 메모리 ID (UUID 형식)

        Raises:
            ValueError: content가 비어있는 경우

        Examples:
            >>> memory_id = memory.add("사용자는 Python 개발자")
            >>> memory_id = memory.add("임시 메모", ttl=3600)  # 1시간 후 만료
        """
        if not content:
            raise ValueError("content는 비어있을 수 없습니다")

        if metadata is None:
            metadata = {}

        metadata.update(
            {
                "layer": layer,
                "created_at": datetime.now().isoformat(),
                "version": 1,
            }
        )

        # TTL 설정
        if ttl is not None:
            metadata["ttl"] = ttl

        memory_id = self.storage.save(content, metadata, self.namespace)
        self._stats["total_memories"] += 1
        self._add_count += 1

        # 자동 레이어 업데이트 (auto_update 모드)
        if self.auto_update and layer == "L2":
            try:
                self.update_layers()
            except Exception:
                pass

        # 인터벌 기반 자동 레이어 업데이트
        if (
            self.auto_layer_interval > 0
            and not self.auto_update
            and self._add_count % self.auto_layer_interval == 0
        ):
            try:
                self.update_layers()
            except Exception:
                pass

        # 캐시 무효화
        self._invalidate_cache()

        return memory_id

    def get(self, memory_id: str) -> Optional[Dict]:
        """메모리 조회

        Args:
            memory_id: 메모리 ID

        Returns:
            메모리 데이터 또는 None
        """
        return self.storage.get(memory_id, self.namespace)

    def update(
        self,
        memory_id: str,
        content: Optional[Union[str, Dict]] = None,
        metadata: Optional[Dict] = None,
    ) -> bool:
        """메모리 수정

        Args:
            memory_id: 메모리 ID
            content: 새 내용 (None이면 유지)
            metadata: 새 메타데이터 (None이면 유지)

        Returns:
            성공 여부
        """
        existing = self.storage.get(memory_id, self.namespace)
        if not existing:
            return False

        new_content = content if content is not None else existing.get("content", "")
        new_metadata = (
            metadata if metadata is not None else existing.get("metadata", {})
        )
        new_metadata["updated_at"] = datetime.now().isoformat()
        new_metadata["version"] = existing.get("metadata", {}).get("version", 0) + 1

        result = self.storage.update(
            memory_id, new_content, new_metadata, self.namespace
        )

        if result:
            self._invalidate_cache()

        return result

    def delete(self, memory_id: str) -> bool:
        """메모리 삭제

        Args:
            memory_id: 메모리 ID

        Returns:
            성공 여부
        """
        result = self.storage.delete(memory_id, self.namespace)

        if result:
            for rel in self.storage.get_relationships(
                memory_id, direction="both", namespace=self.namespace
            ):
                self.storage.delete_relationship(
                    rel.from_id, rel.to_id, rel.relation, self.namespace
                )
            self._stats["total_memories"] = max(0, self._stats["total_memories"] - 1)
            self._invalidate_cache()

        return result

    def retrieve(
        self,
        layer: str = "L1",
        time_range: Optional[tuple] = None,
        use_cache: bool = True,
    ) -> str:
        """계층별 메모리 로드 (토큰 절약 핵심!)

        Args:
            layer: 로드할 계층 ("L0", "L1", "L2")
            time_range: (start, end) 시간 범위 (ISO 8601)
            use_cache: 캐시 사용 여부

        Returns:
            메모리 내용 (Markdown 형식)
        """
        cache_key = f"{self.namespace}:{layer}:{time_range}"

        # 캐시 확인
        if use_cache and self.cache_ttl > 0 and cache_key in self._cache:
            content, timestamp = self._cache[cache_key]
            if time.time() - timestamp < self.cache_ttl:
                self._stats["cache_hits"] += 1
                return content

        self._stats["cache_misses"] += 1

        # 계층별 로드
        if layer in ("L0", "L1"):
            content = self.storage.get_layer(layer, time_range, self.namespace)
        else:  # L2
            content = self.storage.get_all(time_range, self.namespace)

        # 캐시 저장
        if use_cache and self.cache_ttl > 0:
            self._cache[cache_key] = (content, time.time())

        return content

    def search(
        self,
        query: str,
        layer: str = "L1",
        limit: int = 5,
        filters: Optional[Dict] = None,
        positive: Optional[List[str]] = None,
        negative: Optional[List[str]] = None,
    ) -> List[Dict]:
        """의미 기반 검색

        Args:
            query: 검색 쿼리 (자연어)
            layer: 검색할 계층
            limit: 반환할 최대 개수
            filters: 메타데이터 필터
            positive: 반드시 포함해야 할 키워드 리스트
            negative: 제외해야 할 키워드 리스트

        Returns:
            검색 결과 리스트 (유사도 순 정렬)

        Examples:
            >>> results = memory.search(
            ...     "프로젝트 결정",
            ...     positive=["minipm", "react"],
            ...     negative=["폐기", "실패"]
            ... )
        """
        return self.storage.search(
            query=query,
            layer=layer,
            limit=limit,
            filters=filters,
            positive=positive,
            negative=negative,
            namespace=self.namespace,
        )

    def smart_search(
        self,
        query: str,
        layer: str = "L1",
        limit: int = 5,
        use_llm: bool = False,
    ) -> List[Dict]:
        """스마트 검색 (자동 쿼리 분석)

        자연어 쿼리를 자동으로 분석하여 positive/negative 필터 적용.

        Args:
            query: 자연어 쿼리 (예: "React 프로젝트 찾아줘. 실패한 건 제외")
            layer: 검색 대상 계층
            limit: 반환 개수
            use_llm: LLM 사용 여부 (기본 False, rule-based)

        Returns:
            검색 결과 리스트

        Examples:
            >>> results = memory.smart_search(
            ...     "MiniPM 프로젝트 결정 사항. 폐기된 건 빼고"
            ... )
            >>> # 자동으로 positive=['MiniPM', '프로젝트', '결정']
            >>> #          negative=['폐기'] 적용
        """
        # 쿼리 분석
        analyzed = self.query_analyzer.analyze(query, use_llm=use_llm)

        # 분석된 파라미터로 검색
        return self.search(
            query=analyzed["query"],
            layer=layer,
            limit=limit,
            filters=analyzed.get("filters", {}),
            positive=analyzed.get("positive"),
            negative=analyzed.get("negative"),
        )

    def offload_context(
        self,
        label: str,
        content: str,
        metadata: Optional[Dict] = None,
    ) -> Dict:
        """긴 단기 컨텍스트를 외부 참조로 저장하고 Mermaid symbol을 반환합니다.

        FileStorage에서는 원문을 `refs/*.jsonl`에 저장하고, agent context에는
        compact Mermaid node와 `source_ref`만 넣을 수 있게 합니다.
        """
        result = self.storage.offload_context(
            label=label,
            content=content,
            metadata=metadata,
            namespace=self.namespace,
        )
        self._invalidate_cache()
        return result

    def resolve_source_ref(self, source_ref: str) -> Optional[Dict]:
        """검색 결과나 offload 결과의 source_ref로 원문을 조회합니다."""
        return self.storage.resolve_source_ref(source_ref, self.namespace)

    def extract_scenarios(self, limit: int = 10) -> List[Dict]:
        """L2 메모리를 scenario/category 단위로 묶어 provenance와 함께 반환합니다."""
        groups: Dict[str, Dict] = {}
        for memory in self.storage.get_all_raw(namespace=self.namespace):
            metadata = memory.get("metadata", {})
            scenario = str(
                metadata.get("scenario")
                or metadata.get("project")
                or metadata.get("category")
                or "general"
            )
            group = groups.setdefault(
                scenario,
                {
                    "scenario": scenario,
                    "summary": "",
                    "evidence": [],
                },
            )
            if not group["summary"]:
                group["summary"] = self._content_preview(memory.get("content", ""))
            group["evidence"].append(self._evidence_ref(memory))

        scenarios = sorted(
            groups.values(),
            key=lambda item: (-len(item["evidence"]), item["scenario"]),
        )
        return scenarios[:limit]

    def extract_persona(self, limit: int = 20) -> Dict:
        """사용자 선호/제약/프로필 후보를 provenance와 함께 추출합니다."""
        facts = []
        for memory in self.storage.get_all_raw(namespace=self.namespace):
            if not self._looks_like_persona(memory):
                continue
            facts.append(
                {
                    "fact": self._content_preview(memory.get("content", "")),
                    "evidence": self._evidence_ref(memory),
                }
            )
            if len(facts) >= limit:
                break

        return {
            "persona": facts,
            "evidence_count": len(facts),
            "namespace": self.namespace,
        }

    def update_layers(self) -> Dict[str, Union[int, str]]:
        """L0/L1/L2 재생성 (토큰 절약 최적화)

        Returns:
            각 계층별 토큰 수 추정치
        """
        all_memories_raw = self.storage.get_all_raw(namespace=self.namespace)

        if not all_memories_raw:
            return {"L0": 0, "L1": 0, "L2": 0, "savings": "0%"}

        l2_content = self.layers.generate_L2(all_memories_raw)
        l1_content = self.layers.generate_L1(l2_content)
        l0_content = self.layers.generate_L0(l1_content)

        self.storage.save_layer("L0", l0_content, self.namespace)
        self.storage.save_layer("L1", l1_content, self.namespace)

        self._invalidate_cache()

        l0_tokens = self._count_tokens(l0_content)
        l1_tokens = self._count_tokens(l1_content)
        l2_tokens = self._count_tokens(l2_content)

        savings = f"{(1 - l0_tokens / l2_tokens) * 100:.1f}%" if l2_tokens > 0 else "0%"

        return {
            "L0": l0_tokens,
            "L1": l1_tokens,
            "L2": l2_tokens,
            "savings": savings,
        }

    def cleanup(self) -> int:
        """만료된 메모리 정리

        Returns:
            삭제된 메모리 수
        """
        deleted = self.storage.cleanup_expired(self.namespace)
        if deleted > 0:
            self._stats["total_memories"] = max(
                0, self._stats["total_memories"] - deleted
            )
            self._invalidate_cache()
        return deleted

    def list_namespaces(self) -> List[str]:
        """사용 가능한 네임스페이스 목록"""
        return self.storage.list_namespaces()

    def add_relationship(
        self,
        from_id: str,
        to_id: str,
        relation: Union[RelationType, str],
        weight: float = 1.0,
        metadata: Optional[Dict] = None,
    ) -> bool:
        """메모리 간 관계 추가

        Args:
            from_id: 출발 메모리 ID
            to_id: 도착 메모리 ID
            relation: 관계 타입 (RelationType 또는 문자열)
            weight: 관계 강도 (0.0~1.0)
            metadata: 추가 메타데이터

        Returns:
            성공 여부

        Examples:
            >>> memory.add_relationship(
            ...     "mem-123",
            ...     "mem-456",
            ...     RelationType.SIMILAR_TO,
            ...     weight=0.85
            ... )
        """
        if isinstance(relation, str):
            relation = RelationType(relation)

        rel = Relationship(from_id, to_id, relation, weight, metadata or {})
        return self.storage.add_relationship(rel, self.namespace)

    def get_relationships(
        self,
        memory_id: str,
        direction: str = "both",
        relation: Optional[Union[RelationType, str]] = None,
    ) -> List[Relationship]:
        """메모리의 관계 조회

        Args:
            memory_id: 메모리 ID
            direction: "outgoing" (나가는), "incoming" (들어오는), "both" (양방향)
            relation: 특정 관계 타입만 필터링 (None이면 전체)

        Returns:
            관계 리스트

        Examples:
            >>> rels = memory.get_relationships("mem-123")
            >>> similar = memory.get_relationships(
            ...     "mem-123",
            ...     relation=RelationType.SIMILAR_TO
            ... )
        """
        if isinstance(relation, str):
            relation = RelationType(relation)

        return self.storage.get_relationships(
            memory_id, direction, relation, self.namespace
        )

    def get_related(
        self,
        memory_id: str,
        depth: int = 1,
        relation: Optional[Union[RelationType, str]] = None,
    ) -> List[Dict]:
        """연결된 메모리 조회 (그래프 탐색)

        Args:
            memory_id: 시작 메모리 ID
            depth: 탐색 깊이 (1=직접 연결, 2=2단계 연결)
            relation: 특정 관계 타입만 따라가기

        Returns:
            연결된 메모리 리스트 (관계 정보 포함)

        Examples:
            >>> related = memory.get_related("mem-123", depth=2)
            >>> for item in related:
            ...     print(f"{item['id']}: {item['relation']} (w={item['weight']})")
        """
        if isinstance(relation, str):
            relation = RelationType(relation)

        visited = set()
        result: List[Dict] = []

        def traverse(current_id: str, current_depth: int) -> None:
            if current_depth > depth or current_id in visited:
                return

            visited.add(current_id)

            # 현재 노드의 관계 조회
            rels = self.get_relationships(
                current_id, direction="outgoing", relation=relation
            )

            for rel in rels:
                target_id = rel.to_id
                if target_id not in visited:
                    # 메모리 데이터 조회
                    memory_data = self.get(target_id)
                    if memory_data:
                        result.append(
                            {
                                **memory_data,
                                "relation": rel.relation.value,
                                "weight": rel.weight,
                                "depth": current_depth,
                            }
                        )

                    # 재귀적으로 탐색
                    if current_depth < depth:
                        traverse(target_id, current_depth + 1)

        traverse(memory_id, 1)
        return result

    def get_stats(self) -> Dict[str, Union[int, float, str]]:
        """메모리 통계 조회"""
        total_requests = self._stats["cache_hits"] + self._stats["cache_misses"]
        cache_hit_rate = (
            self._stats["cache_hits"] / total_requests if total_requests > 0 else 0.0
        )
        total_memories = len(self.storage.get_all_raw(namespace=self.namespace))

        return {
            "total_memories": total_memories,
            "cache_hits": self._stats["cache_hits"],
            "cache_misses": self._stats["cache_misses"],
            "cache_hit_rate": cast(float, cache_hit_rate),
            "namespace": self.namespace,
        }

    def _invalidate_cache(self) -> None:
        """캐시 무효화"""
        self._cache.clear()

    def _count_tokens(self, text: str) -> int:
        """토큰 수 추정 (간단한 휴리스틱)"""
        if not text:
            return 0
        return int(len(text.split()) * 1.3)

    def _content_preview(self, content: Union[str, Dict]) -> str:
        if isinstance(content, dict):
            import json

            text = json.dumps(content, ensure_ascii=False)
        else:
            text = str(content)
        text = " ".join(text.split())
        if len(text) > 180:
            return text[:177].rstrip() + "..."
        return text

    def _evidence_ref(self, memory: Dict) -> Dict:
        metadata = memory.get("metadata", {})
        return {
            "id": memory.get("id", ""),
            "node_id": memory.get("node_id") or metadata.get("node_id", ""),
            "source_ref": memory.get("source_ref") or metadata.get("source_ref", ""),
            "created_at": memory.get("created_at", ""),
        }

    def _looks_like_persona(self, memory: Dict) -> bool:
        metadata = memory.get("metadata", {})
        tags = {str(tag).lower() for tag in metadata.get("tags", [])}
        category = str(metadata.get("category", "")).lower()
        persona_markers = {
            "persona",
            "profile",
            "preference",
            "preferences",
            "constraint",
            "user",
            "사용자",
            "선호",
            "제약",
            "프로필",
        }
        if category in persona_markers or tags.intersection(persona_markers):
            return True

        content = self._content_preview(memory.get("content", "")).lower()
        return any(
            marker in content
            for marker in (
                "prefers",
                "preference",
                "likes",
                "does not want",
                "사용자는",
                "선호",
                "싫어",
                "원하지",
            )
        )
