"""
MemMini Storage Interface

모든 저장소 백엔드가 구현해야 하는 추상 인터페이스.
"""

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Dict, List, Optional, Union

if TYPE_CHECKING:
    from memmini.core.relationship import Relationship, RelationType


class MemoryStorage(ABC):
    """저장소 추상화 인터페이스

    Implementations:
        - FileStorage: 파일 시스템
        - VectorStorage: ChromaDB
        - HybridStorage: 파일 + 벡터
    """

    @abstractmethod
    def save(
        self,
        content: Union[str, Dict],
        metadata: Dict,
        namespace: str = "default",
    ) -> str:
        """메모리 저장

        Args:
            content: 메모리 내용 (문자열 또는 딕셔너리)
            metadata: 메타데이터
            namespace: 네임스페이스 (사용자/에이전트 분리)

        Returns:
            memory_id: 생성된 메모리 ID
        """
        pass

    @abstractmethod
    def get(self, memory_id: str, namespace: str = "default") -> Optional[Dict]:
        """메모리 조회

        Args:
            memory_id: 메모리 ID
            namespace: 네임스페이스

        Returns:
            메모리 데이터 또는 None
        """
        pass

    @abstractmethod
    def update(
        self,
        memory_id: str,
        content: Union[str, Dict],
        metadata: Optional[Dict] = None,
        namespace: str = "default",
    ) -> bool:
        """메모리 수정

        Args:
            memory_id: 메모리 ID
            content: 새 내용
            metadata: 새 메타데이터 (None이면 유지)
            namespace: 네임스페이스

        Returns:
            성공 여부
        """
        pass

    @abstractmethod
    def delete(self, memory_id: str, namespace: str = "default") -> bool:
        """메모리 삭제

        Args:
            memory_id: 메모리 ID
            namespace: 네임스페이스

        Returns:
            성공 여부
        """
        pass

    @abstractmethod
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
        """의미 기반 검색

        Args:
            query: 검색 쿼리
            layer: 검색 대상 계층
            limit: 반환 개수
            filters: 메타데이터 필터
            positive: 반드시 포함해야 할 키워드
            negative: 제외해야 할 키워드
            namespace: 네임스페이스

        Returns:
            검색 결과 리스트 (유사도 순)
        """
        pass

    @abstractmethod
    def get_layer(
        self,
        layer: str,
        time_range: Optional[tuple] = None,
        namespace: str = "default",
    ) -> str:
        """계층별 메모리 로드 (L0/L1)

        Args:
            layer: "L0" 또는 "L1"
            time_range: (start, end) 시간 범위
            namespace: 네임스페이스

        Returns:
            계층 내용 (Markdown)
        """
        pass

    @abstractmethod
    def save_layer(self, layer: str, content: str, namespace: str = "default") -> None:
        """계층별 메모리 저장 (L0/L1)

        Args:
            layer: "L0" 또는 "L1"
            content: 저장할 내용
            namespace: 네임스페이스
        """
        pass

    @abstractmethod
    def get_all(
        self,
        time_range: Optional[tuple] = None,
        namespace: str = "default",
    ) -> str:
        """전체 메모리 로드 (L2)

        Args:
            time_range: (start, end) 시간 범위
            namespace: 네임스페이스

        Returns:
            전체 메모리 (Markdown)
        """
        pass

    def get_all_raw(
        self,
        time_range: Optional[tuple] = None,
        namespace: str = "default",
    ) -> List[Dict]:
        """전체 메모리를 원시 딕셔너리 리스트로 반환

        Args:
            time_range: (start, end) 시간 범위
            namespace: 네임스페이스

        Returns:
            메모리 딕셔너리 리스트
        """
        return []

    def cleanup_expired(self, namespace: str = "default") -> int:
        """만료된 메모리 정리

        Args:
            namespace: 네임스페이스

        Returns:
            삭제된 메모리 수
        """
        return 0

    def offload_context(
        self,
        label: str,
        content: str,
        metadata: Optional[Dict] = None,
        namespace: str = "default",
    ) -> Dict:
        """긴 단기 컨텍스트를 외부 참조로 저장

        지원하지 않는 저장소는 NotImplementedError를 발생시킵니다.
        """
        raise NotImplementedError("이 저장소는 context offload를 지원하지 않습니다")

    def resolve_source_ref(
        self,
        source_ref: str,
        namespace: str = "default",
    ) -> Optional[Dict]:
        """source_ref로 원문을 조회

        지원하지 않는 저장소는 None을 반환합니다.
        """
        return None

    def list_namespaces(self) -> List[str]:
        """사용 가능한 네임스페이스 목록 반환

        Returns:
            네임스페이스 이름 리스트
        """
        return ["default"]

    def add_relationship(
        self,
        relationship: "Relationship",
        namespace: str = "default",
    ) -> bool:
        """메모리 간 관계 추가

        Args:
            relationship: 관계 객체
            namespace: 네임스페이스

        Returns:
            성공 여부
        """
        return False

    def get_relationships(
        self,
        memory_id: str,
        direction: str = "both",
        relation: Optional["RelationType"] = None,
        namespace: str = "default",
    ) -> List["Relationship"]:
        """메모리의 관계 조회

        Args:
            memory_id: 메모리 ID
            direction: "outgoing", "incoming", "both"
            relation: 특정 관계 타입 필터
            namespace: 네임스페이스

        Returns:
            관계 리스트
        """
        return []

    def delete_relationship(
        self,
        from_id: str,
        to_id: str,
        relation: Optional["RelationType"] = None,
        namespace: str = "default",
    ) -> bool:
        """관계 삭제

        Args:
            from_id: 출발 메모리 ID
            to_id: 도착 메모리 ID
            relation: 특정 관계만 삭제 (None이면 전체)
            namespace: 네임스페이스

        Returns:
            성공 여부
        """
        return False
