"""
MemMini URI Resolver

mini:// URI 스킴을 통한 메모리 접근.
"""

from typing import Dict
from urllib.parse import parse_qs, urlparse

from memmini.core.memory_core import MemoryCore


class MiniResolver:
    """mini:// URI Resolver

    mini:// URI를 파싱하여 MemoryCore 메서드를 호출합니다.

    지원 URI:
        - mini://L0              → retrieve(layer="L0")
        - mini://L1              → retrieve(layer="L1")
        - mini://L2              → retrieve(layer="L2")
        - mini://search?q=키워드  → search(query)
        - mini://search?q=키워드&limit=10
        - mini://mem/{id}        → get(memory_id)
        - mini://stats           → get_stats()
        - mini://namespaces      → list_namespaces()

    Examples:
        >>> resolver = MiniResolver(core)
        >>> l0 = resolver.resolve("mini://L0")
        >>> results = resolver.resolve("mini://search?q=Python&limit=3")
    """

    def __init__(self, core: MemoryCore):
        """MiniResolver 초기화

        Args:
            core: MemoryCore 인스턴스
        """
        self.core = core

    def resolve(self, uri: str) -> str:
        """URI를 파싱하여 결과 반환

        Args:
            uri: mini:// URI

        Returns:
            결과 문자열 (Markdown 또는 JSON)

        Raises:
            ValueError: 잘못된 URI 형식
        """
        parsed = urlparse(uri)

        if parsed.scheme != "mini":
            raise ValueError(f"지원하지 않는 스킴: {parsed.scheme} (mini:// 만 지원)")

        # netloc + path 결합 (mini://mem/id → netloc="mem", path="/id")
        path = parsed.netloc
        if parsed.path:
            path = path + parsed.path
        path = path.strip("/")

        # 쿼리 파라미터 파싱
        params = parse_qs(parsed.query)

        return self._dispatch(path, params)

    def _dispatch(self, path: str, params: Dict) -> str:
        """경로에 따라 적절한 메서드 호출"""

        # Layer 조회: mini://L0, mini://L1, mini://L2
        if path.upper() in ("L0", "L1", "L2"):
            return self._resolve_layer(path.upper())

        # 검색: mini://search?q=키워드
        if path == "search":
            return self._resolve_search(params)

        # 개별 메모리: mini://mem/{id}
        if path.startswith("mem/"):
            memory_id = path[4:]  # "mem/" 제거
            return self._resolve_mem(memory_id)

        # 통계: mini://stats
        if path == "stats":
            return self._resolve_stats()

        # 네임스페이스: mini://namespaces
        if path == "namespaces":
            return self._resolve_namespaces()

        raise ValueError(f"알 수 없는 경로: {path}")

    def _resolve_layer(self, layer: str) -> str:
        """계층별 메모리 조회"""
        content = self.core.retrieve(layer=layer)
        return content if content else f"({layer} 비어있음)"

    def _resolve_search(self, params: Dict) -> str:
        """검색 수행"""
        query_list = params.get("q", [""])
        query = query_list[0] if query_list else ""

        if not query:
            raise ValueError("검색어 필요: mini://search?q=키워드")

        limit_list = params.get("limit", ["5"])
        limit = int(limit_list[0])

        results = self.core.search(query=query, limit=limit)

        if not results:
            return f"검색 결과 없음: {query}"

        import json

        lines = [f"# 검색 결과: {query} ({len(results)}건)\n"]
        for r in results:
            content = r.get("content", "")
            if isinstance(content, dict):
                content = json.dumps(content, ensure_ascii=False)
            mem_id = r.get("id", "?")
            lines.append(f"- **{mem_id}**: {content[:100]}")

        return "\n".join(lines)

    def _resolve_mem(self, memory_id: str) -> str:
        """개별 메모리 조회"""
        import json

        data = self.core.get(memory_id)
        if not data:
            return f"메모리 없음: {memory_id}"

        return json.dumps(data, ensure_ascii=False, indent=2)

    def _resolve_stats(self) -> str:
        """통계 조회"""

        stats = self.core.get_stats()
        lines = ["# MemMini 통계\n"]
        for key, value in stats.items():
            lines.append(f"- **{key}**: {value}")
        return "\n".join(lines)

    def _resolve_namespaces(self) -> str:
        """네임스페이스 목록"""
        namespaces = self.core.list_namespaces()
        lines = ["# 네임스페이스\n"]
        for ns in namespaces:
            lines.append(f"- {ns}")
        return "\n".join(lines)
