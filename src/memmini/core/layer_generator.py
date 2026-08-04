"""
MemMini Layer Generator

L0/L1/L2 계층 생성기.
LLM 또는 rule-based 방식으로 메모리 요약을 생성합니다.
"""

import re
from typing import Dict, List, Optional, Protocol, runtime_checkable


@runtime_checkable
class LLMProvider(Protocol):
    """LLM 추상화 (플랫폼 독립적)

    generate() 메서드를 제공하는 외부 LLM provider를 주입할 수 있습니다.

    Examples:
        >>> class OllamaProvider:
        ...     def generate(self, prompt, max_tokens=100, temperature=0.7):
        ...         # Ollama API 호출
        ...         return "요약 결과"
    """

    def generate(
        self,
        prompt: str,
        max_tokens: int = 100,
        temperature: float = 0.7,
    ) -> str:
        """텍스트 생성"""
        ...


class LayerGenerator:
    """L0/L1/L2 계층 생성기

    LLM 또는 rule-based 방식으로 메모리 요약 생성.

    Examples:
        >>> # LLM 없이 (rule-based만)
        >>> generator = LayerGenerator()

        >>> # LLM 사용
        >>> generator = LayerGenerator(llm=my_llm_provider)
    """

    def __init__(
        self,
        llm: Optional[LLMProvider] = None,
        use_rule_based: bool = True,
    ):
        """LayerGenerator 초기화

        Args:
            llm: LLM 제공자 (None이면 rule-based만 사용)
            use_rule_based: LLM 실패 시 rule-based 폴백 사용 여부
        """
        self.llm = llm
        self.use_rule_based = use_rule_based

    def generate_L0(self, l1_content: str) -> str:
        """L0: 한 줄 요약 생성 (~100 tokens)

        L1 내용에서 핵심 정보를 추출하여 한 줄로 압축합니다.

        Args:
            l1_content: L1 계층 내용

        Returns:
            한 줄 요약 문자열

        Examples:
            >>> generator = LayerGenerator()
            >>> l0 = generator.generate_L0("## 주요 결정사항\\n- L0/L1/L2 채택")
            >>> len(l0) < 300
            True
        """
        if not l1_content or not l1_content.strip():
            return "메모리 없음"

        if self.llm:
            try:
                prompt = (
                    "다음 메모리 요약을 한 줄로 압축하세요 (100 tokens 이내).\n"
                    "핵심 정보만 포함하고, 날짜/이벤트/결정사항 중심으로 "
                    "작성하세요.\n\n"
                    f"{l1_content}\n\n한 줄 요약:"
                )
                return self.llm.generate(prompt, max_tokens=100)
            except Exception:
                if not self.use_rule_based:
                    raise

        # Rule-based: 첫 의미있는 라인 추출 + 날짜 정보
        return self._rule_based_L0(l1_content)

    def generate_L1(self, l2_content: str) -> str:
        """L1: 핵심 요약 생성 (~500 words, ~800 tokens)

        L2 전체 메모리에서 핵심 정보를 추출하여 요약합니다.

        Args:
            l2_content: L2 계층 내용 (전체 메모리)

        Returns:
            핵심 요약 (Markdown 형식)

        Examples:
            >>> generator = LayerGenerator()
            >>> l1 = generator.generate_L1("# 전체 메모리\\n\\n## 2026-02-14\\n내용...")
            >>> len(l1) < len("# 전체 메모리\\n\\n## 2026-02-14\\n내용...")
            True
        """
        if not l2_content or not l2_content.strip():
            return "메모리 없음"

        if self.llm:
            try:
                prompt = (
                    "다음 전체 메모리를 500 단어로 요약하세요.\n"
                    "다음 섹션을 포함하세요:\n"
                    "- 주요 결정사항\n"
                    "- 핵심 액션 아이템\n"
                    "- 중요 인사이트\n"
                    "- 미해결 이슈\n\n"
                    f"{l2_content}\n\n핵심 요약 (Markdown):"
                )
                return self.llm.generate(prompt, max_tokens=800)
            except Exception:
                if not self.use_rule_based:
                    raise

        # Rule-based: 섹션별 첫 문단 추출
        return self._rule_based_L1(l2_content)

    def generate_L2(self, raw_memories: List[Dict]) -> str:
        """L2: 전체 내용 생성 (시간순 정렬 + Markdown 변환)

        원시 메모리 리스트를 읽기 쉬운 Markdown 형식으로 변환합니다.

        Args:
            raw_memories: 원시 메모리 딕셔너리 리스트

        Returns:
            전체 메모리 (Markdown)

        Examples:
            >>> generator = LayerGenerator()
            >>> raw = [{"content": "테스트", "created_at": "2026-02-14T10:00:00"}]
            >>> l2 = generator.generate_L2(raw)
            >>> "테스트" in l2
            True
        """
        if not raw_memories:
            return "# 전체 메모리\n\n메모리 없음"

        # 시간순 정렬 (최신 우선)
        sorted_memories = sorted(
            raw_memories,
            key=lambda m: m.get("created_at", ""),
            reverse=True,
        )

        markdown = "# 전체 메모리\n\n"

        for mem in sorted_memories:
            timestamp = mem.get("created_at", "Unknown")
            content = mem.get("content", "")
            metadata = mem.get("metadata", {})

            markdown += f"## {timestamp}\n"

            # 태그 표시
            tags = metadata.get("tags", [])
            if tags:
                tags_str = ", ".join(tags)
                markdown += f"**태그:** {tags_str}\n\n"

            # 카테고리 표시
            category = metadata.get("category")
            if category:
                markdown += f"**카테고리:** {category}\n\n"

            # content가 dict인 경우 문자열로 변환
            if isinstance(content, dict):
                import json

                content = json.dumps(content, ensure_ascii=False, indent=2)

            markdown += f"{content}\n\n---\n\n"

        return markdown

    def _rule_based_L0(self, l1_content: str) -> str:
        """Rule-based L0 생성: 첫 의미있는 라인 + 날짜"""
        lines = [line.strip() for line in l1_content.split("\n") if line.strip()]

        # Markdown 헤더 제거하고 의미있는 첫 라인 찾기
        first_meaningful = ""
        for line in lines:
            # 헤더나 구분선 건너뛰기
            if line.startswith("#") or line.startswith("---") or line.startswith("==="):
                continue
            # 리스트 아이템이면 마커 제거
            cleaned = re.sub(r"^[-*]\s+", "", line)
            if cleaned:
                first_meaningful = cleaned[:200]
                break

        if not first_meaningful:
            first_meaningful = lines[0][:200] if lines else "메모리 없음"

        # 날짜 추출 시도
        date_match = re.search(r"\d{4}-\d{2}-\d{2}", l1_content)
        if date_match:
            return f"{date_match.group()}: {first_meaningful}"

        return first_meaningful

    def _rule_based_L1(self, l2_content: str) -> str:
        """Rule-based L1 생성: 섹션별 첫 문단 추출"""
        sections = l2_content.split("\n## ")
        summaries = []

        for i, section in enumerate(sections[:10]):  # 최대 10개 섹션
            paragraphs = section.split("\n\n")
            if not paragraphs:
                continue

            header = paragraphs[0].strip()
            # 첫 섹션은 # 헤더일 수 있음
            if i == 0 and header.startswith("# "):
                header = header[2:]

            first_para = ""
            if len(paragraphs) > 1:
                first_para = paragraphs[1][:200].strip()

            if i == 0:
                summaries.append(f"## {header}\n{first_para}")
            else:
                summaries.append(f"## {header}\n{first_para}")

        return "\n\n".join(summaries) if summaries else l2_content[:500]
