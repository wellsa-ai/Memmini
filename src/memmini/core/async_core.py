"""
MemMini Async Core

비동기 메모리 엔진 — MemoryCore의 async 래퍼.
asyncio.to_thread()를 사용하여 기존 sync 코드를 재활용합니다.
"""

import asyncio
from typing import Dict, List, Optional, Union

from memmini.core.layer_generator import LayerGenerator
from memmini.core.memory_core import MemoryCore
from memmini.core.storage import MemoryStorage


class AsyncMemoryCore:
    """비동기 MemMini 메모리 엔진

    MemoryCore의 모든 기능을 async/await로 제공합니다.
    내부적으로 asyncio.to_thread()를 사용하여 I/O blocking을 방지합니다.

    Examples:
        >>> from memmini.core.async_core import AsyncMemoryCore
        >>> from memmini.storage.file import FileStorage
        >>>
        >>> async def main():
        ...     memory = AsyncMemoryCore(storage=FileStorage())
        ...     mem_id = await memory.add("사용자는 Python 개발자")
        ...     l0 = await memory.retrieve(layer="L0")

    Attributes:
        core: 내부 동기 MemoryCore 인스턴스
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
        """AsyncMemoryCore 초기화

        Args:
            storage: 저장소 백엔드
            layer_generator: L0/L1/L2 생성기
            auto_layer_update: 자동 레이어 업데이트 여부
            cache_ttl: 캐시 유효 시간 (초)
            namespace: 네임스페이스
            auto_layer_interval: N개마다 자동 update_layers()
        """
        self.core = MemoryCore(
            storage=storage,
            layer_generator=layer_generator,
            auto_layer_update=auto_layer_update,
            cache_ttl=cache_ttl,
            namespace=namespace,
            auto_layer_interval=auto_layer_interval,
        )

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
    ) -> "AsyncMemoryCore":
        """파일 저장소 기반 AsyncMemoryCore를 짧게 생성합니다."""
        from memmini.storage.file import FileStorage

        return cls(
            storage=FileStorage(base_path=path),
            layer_generator=layer_generator,
            auto_layer_update=auto_layer_update,
            cache_ttl=cache_ttl,
            namespace=namespace,
            auto_layer_interval=auto_layer_interval,
        )

    async def add(
        self,
        content: Union[str, Dict],
        metadata: Optional[Dict] = None,
        layer: str = "L2",
        ttl: Optional[int] = None,
    ) -> str:
        """메모리 비동기 추가

        Args:
            content: 메모리 내용
            metadata: 메타데이터
            layer: 저장 계층
            ttl: 메모리 유효 시간 (초)

        Returns:
            memory_id
        """
        return await asyncio.to_thread(self.core.add, content, metadata, layer, ttl)

    async def get(self, memory_id: str) -> Optional[Dict]:
        """메모리 비동기 조회"""
        return await asyncio.to_thread(self.core.get, memory_id)

    async def update(
        self,
        memory_id: str,
        content: Optional[Union[str, Dict]] = None,
        metadata: Optional[Dict] = None,
    ) -> bool:
        """메모리 비동기 수정"""
        return await asyncio.to_thread(self.core.update, memory_id, content, metadata)

    async def delete(self, memory_id: str) -> bool:
        """메모리 비동기 삭제"""
        return await asyncio.to_thread(self.core.delete, memory_id)

    async def retrieve(
        self,
        layer: str = "L1",
        time_range: Optional[tuple] = None,
        use_cache: bool = True,
    ) -> str:
        """계층별 메모리 비동기 로드"""
        return await asyncio.to_thread(self.core.retrieve, layer, time_range, use_cache)

    async def search(
        self,
        query: str,
        layer: str = "L1",
        limit: int = 5,
        filters: Optional[Dict] = None,
        positive: Optional[List[str]] = None,
        negative: Optional[List[str]] = None,
    ) -> List[Dict]:
        """메모리 비동기 검색"""
        return await asyncio.to_thread(
            self.core.search, query, layer, limit, filters, positive, negative
        )

    async def smart_search(
        self,
        query: str,
        layer: str = "L1",
        limit: int = 5,
        use_llm: bool = False,
    ) -> List[Dict]:
        """자연어 쿼리를 분석해 비동기 검색합니다."""
        return await asyncio.to_thread(
            self.core.smart_search, query, layer, limit, use_llm
        )

    async def offload_context(
        self,
        label: str,
        content: str,
        metadata: Optional[Dict] = None,
    ) -> Dict:
        """긴 단기 컨텍스트를 외부 참조로 비동기 저장합니다."""
        return await asyncio.to_thread(
            self.core.offload_context, label, content, metadata
        )

    async def resolve_source_ref(self, source_ref: str) -> Optional[Dict]:
        """source_ref로 원문을 비동기 조회합니다."""
        return await asyncio.to_thread(self.core.resolve_source_ref, source_ref)

    async def extract_scenarios(self, limit: int = 10) -> List[Dict]:
        """scenario/category 추출을 비동기로 실행합니다."""
        return await asyncio.to_thread(self.core.extract_scenarios, limit)

    async def extract_persona(self, limit: int = 20) -> Dict:
        """persona 후보 추출을 비동기로 실행합니다."""
        return await asyncio.to_thread(self.core.extract_persona, limit)

    async def update_layers(self) -> Dict[str, Union[int, str]]:
        """L0/L1/L2 비동기 재생성"""
        return await asyncio.to_thread(self.core.update_layers)

    async def cleanup(self) -> int:
        """만료된 메모리 비동기 정리"""
        return await asyncio.to_thread(self.core.cleanup)

    async def get_stats(self) -> Dict:
        """통계 비동기 조회"""
        return await asyncio.to_thread(self.core.get_stats)

    async def list_namespaces(self) -> List[str]:
        """네임스페이스 목록 비동기 조회"""
        return await asyncio.to_thread(self.core.list_namespaces)
