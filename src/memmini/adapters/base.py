"""
MemMini Adapter Base

플랫폼별 어댑터의 추상 베이스 클래스.
"""

from abc import ABC, abstractmethod
from typing import Any

from memmini.core.memory_core import MemoryCore


class MemoryAdapter(ABC):
    """플랫폼별 어댑터 베이스

    MemoryCore를 다양한 AI 플랫폼과 통합하기 위한 추상 클래스.

    Adapters:
        - OpenClawAdapter: OpenClaw MEMORY.md 통합
        - LangChainAdapter: LangChain BaseMemory (Phase 2)
        - AutoGenAdapter: AutoGen ConversableAgent (Phase 2)
    """

    def __init__(self, core: MemoryCore):
        """MemoryAdapter 초기화

        Args:
            core: MemoryCore 인스턴스
        """
        self.core = core

    @abstractmethod
    def sync_to_platform(self) -> None:
        """MemMini → 플랫폼 동기화"""
        pass

    @abstractmethod
    def sync_from_platform(self) -> None:
        """플랫폼 → MemMini 동기화"""
        pass

    @abstractmethod
    def get_platform_object(self) -> Any:
        """플랫폼 네이티브 객체 반환"""
        pass
