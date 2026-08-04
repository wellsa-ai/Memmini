"""
MemMini Relationship Types

메모리 간 관계 타입 정의.
"""

from enum import Enum
from typing import Dict, Optional


class RelationType(str, Enum):
    """메모리 간 관계 타입

    Examples:
        >>> RelationType.SIMILAR_TO
        'SIMILAR_TO'
    """

    SIMILAR_TO = "SIMILAR_TO"  # 유사한 메모리
    RELATED_TO = "RELATED_TO"  # 관련된 메모리
    CAUSES = "CAUSES"  # 원인-결과
    PART_OF = "PART_OF"  # 부분-전체
    FOLLOWS = "FOLLOWS"  # 시간적 순서
    REFERENCES = "REFERENCES"  # 참조


class Relationship:
    """메모리 관계 표현

    Attributes:
        from_id: 출발 메모리 ID
        to_id: 도착 메모리 ID
        relation: 관계 타입
        weight: 관계 강도 (0.0~1.0)
        metadata: 추가 메타데이터

    Examples:
        >>> rel = Relationship(
        ...     from_id="mem-123",
        ...     to_id="mem-456",
        ...     relation=RelationType.SIMILAR_TO,
        ...     weight=0.85
        ... )
    """

    def __init__(
        self,
        from_id: str,
        to_id: str,
        relation: RelationType,
        weight: float = 1.0,
        metadata: Optional[Dict] = None,
    ):
        self.from_id = from_id
        self.to_id = to_id
        self.relation = relation
        self.weight = max(0.0, min(1.0, weight))  # 0~1 사이로 제한
        self.metadata = metadata or {}

    def to_dict(self) -> Dict:
        """딕셔너리로 변환"""
        return {
            "from_id": self.from_id,
            "to_id": self.to_id,
            "relation": self.relation.value,
            "weight": self.weight,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict) -> "Relationship":
        """딕셔너리에서 생성"""
        return cls(
            from_id=data["from_id"],
            to_id=data["to_id"],
            relation=RelationType(data["relation"]),
            weight=data.get("weight", 1.0),
            metadata=data.get("metadata", {}),
        )

    def __repr__(self) -> str:
        return (
            f"Relationship({self.from_id} -{self.relation.value}-> "
            f"{self.to_id}, w={self.weight:.2f})"
        )
