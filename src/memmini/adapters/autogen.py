"""
MemMini AutoGen Adapter

AutoGen ConversableAgent 통합 — MemMini를 AutoGen 에이전트 메모리로 사용.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from memmini.adapters.base import MemoryAdapter
from memmini.core.memory_core import MemoryCore


class AutoGenAdapter(MemoryAdapter):
    """AutoGen Agent 통합 어댑터

    AutoGen ConversableAgent에 MemMini의 계층형 메모리를 주입합니다.

    Examples:
        >>> from memmini.adapters.autogen import AutoGenAdapter
        >>> from memmini.storage.file import FileStorage
        >>> from memmini.core.memory_core import MemoryCore
        >>>
        >>> core = MemoryCore(storage=FileStorage())
        >>> adapter = AutoGenAdapter(core)
        >>>
        >>> # 메시지 처리 (대화 중 자동 저장)
        >>> adapter.process_message({"role": "user", "content": "Python 사용"})
        >>>
        >>> # 시스템 프롬프트에 메모리 주입
        >>> system_msg = adapter.create_system_message()

    Attributes:
        context_layer: 컨텍스트 로드 시 사용할 계층
        auto_save: 메시지 자동 저장 여부
    """

    def __init__(
        self,
        core: MemoryCore,
        context_layer: str = "L1",
        auto_save: bool = True,
    ):
        """AutoGenAdapter 초기화

        Args:
            core: MemoryCore 인스턴스
            context_layer: 기본 컨텍스트 계층
            auto_save: 메시지 자동 저장 여부
        """
        super().__init__(core)
        self.context_layer = context_layer
        self.auto_save = auto_save

    def process_message(self, message: Dict[str, str]) -> Optional[str]:
        """메시지 처리 및 메모리 저장

        AutoGen 대화 메시지를 MemMini에 저장합니다.

        Args:
            message: {"role": "user"|"assistant", "content": "..."}

        Returns:
            memory_id (auto_save=True일 때) 또는 None
        """
        if not self.auto_save:
            return None

        role = message.get("role", "unknown")
        content = message.get("content", "")

        if not content:
            return None

        memory_id = self.core.add(
            content,
            metadata={
                "source": "autogen",
                "role": role,
                "type": "message",
                "timestamp": datetime.now().isoformat(),
            },
        )

        return memory_id

    def get_context(self, layer: Optional[str] = None) -> str:
        """현재 메모리 컨텍스트 반환

        Args:
            layer: 사용할 계층 (None이면 기본 context_layer)

        Returns:
            메모리 내용 (Markdown)
        """
        target_layer = layer or self.context_layer
        return self.core.retrieve(layer=target_layer)

    def create_system_message(
        self,
        base_prompt: str = "",
        layer: Optional[str] = None,
    ) -> str:
        """메모리 기반 시스템 메시지 생성

        L0/L1 메모리를 포함한 system prompt를 생성합니다.

        Args:
            base_prompt: 기본 시스템 프롬프트
            layer: 사용할 계층 (None이면 context_layer)

        Returns:
            메모리가 포함된 시스템 메시지
        """
        context = self.get_context(layer)

        parts = []
        if base_prompt:
            parts.append(base_prompt)

        if context.strip():
            parts.append(
                "\n## 메모리 컨텍스트\n"
                "다음은 이전 대화에서 기억된 정보입니다:\n\n"
                f"{context}"
            )

        return "\n".join(parts) if parts else ""

    def get_relevant_context(self, query: str, limit: int = 5) -> List[Dict]:
        """쿼리와 관련된 메모리 검색

        Args:
            query: 검색 쿼리
            limit: 반환 개수

        Returns:
            관련 메모리 리스트
        """
        return self.core.search(query=query, limit=limit)

    def sync_to_platform(self) -> None:
        """MemMini → AutoGen (create_system_message에서 처리)"""
        pass

    def sync_from_platform(self) -> None:
        """AutoGen → MemMini (process_message에서 처리)"""
        pass

    def get_platform_object(self) -> Any:
        """AutoGen 호환 객체 반환"""
        return self
