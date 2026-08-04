"""
MemMini LangChain Adapter

LangChain BaseMemory 통합 — MemMini를 LangChain 대화 메모리로 사용.
"""

from typing import Any, Dict, List, Optional

from memmini.adapters.base import MemoryAdapter
from memmini.core.memory_core import MemoryCore


class LangChainAdapter(MemoryAdapter):
    """LangChain Memory 통합 어댑터

    LangChain의 BaseMemory 인터페이스를 구현하여
    MemMini를 LangChain 대화 체인의 메모리로 사용합니다.

    Examples:
        >>> from memmini.adapters.langchain import LangChainAdapter
        >>> from memmini.storage.file import FileStorage
        >>> from memmini.core.memory_core import MemoryCore
        >>>
        >>> core = MemoryCore(storage=FileStorage())
        >>> adapter = LangChainAdapter(core)
        >>>
        >>> # LangChain 체인에서 사용
        >>> memory_vars = adapter.load_memory_variables({})
        >>> adapter.save_context(
        ...     {"input": "안녕하세요"},
        ...     {"output": "안녕하세요! 무엇을 도와드릴까요?"}
        ... )

    Attributes:
        memory_key: LangChain에서 사용할 메모리 변수 이름
        layer: 메모리 로드 시 사용할 계층
        input_key: 입력 키
        output_key: 출력 키
    """

    def __init__(
        self,
        core: MemoryCore,
        memory_key: str = "history",
        layer: str = "L1",
        input_key: str = "input",
        output_key: str = "output",
    ):
        """LangChainAdapter 초기화

        Args:
            core: MemoryCore 인스턴스
            memory_key: 메모리 변수 키 이름
            layer: 기본 로드 계층 (L0/L1/L2)
            input_key: 입력 딕셔너리 키
            output_key: 출력 딕셔너리 키
        """
        super().__init__(core)
        self.memory_key = memory_key
        self.layer = layer
        self.input_key = input_key
        self.output_key = output_key

    @property
    def memory_variables(self) -> List[str]:
        """LangChain에서 사용하는 메모리 변수 이름 목록"""
        return [self.memory_key]

    def load_memory_variables(
        self, inputs: Optional[Dict[str, Any]] = None
    ) -> Dict[str, str]:
        """메모리 변수 로드 (LangChain 호출)

        지정된 계층의 메모리를 로드하여 딕셔너리로 반환합니다.

        Args:
            inputs: 입력 변수 (무시됨, LangChain 호환용)

        Returns:
            {memory_key: 메모리 내용}
        """
        content = self.core.retrieve(layer=self.layer)
        return {self.memory_key: content}

    def save_context(
        self,
        inputs: Dict[str, Any],
        outputs: Dict[str, str],
    ) -> None:
        """대화 컨텍스트 저장 (LangChain 호출)

        입력/출력 쌍을 MemMini에 저장합니다.

        Args:
            inputs: 사용자 입력 딕셔너리
            outputs: AI 출력 딕셔너리
        """
        input_text = inputs.get(self.input_key, "")
        output_text = outputs.get(self.output_key, "")

        content = f"Human: {input_text}\nAI: {output_text}"

        self.core.add(
            content,
            metadata={
                "source": "langchain",
                "type": "conversation",
            },
        )

    def clear(self) -> None:
        """메모리 초기화

        현재 네임스페이스의 모든 메모리를 삭제합니다.
        """
        all_memories = self.core.storage.get_all_raw(namespace=self.core.namespace)
        for mem in all_memories:
            mem_id = mem.get("id")
            if mem_id:
                self.core.delete(mem_id)

    def sync_to_platform(self) -> None:
        """LangChain → MemMini (자동 save_context에서 처리)"""
        pass

    def sync_from_platform(self) -> None:
        """MemMini → LangChain (load_memory_variables에서 처리)"""
        pass

    def get_platform_object(self) -> Any:
        """LangChain Memory 호환 객체 반환"""
        return self
