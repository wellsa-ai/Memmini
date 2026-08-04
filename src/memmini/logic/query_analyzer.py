"""
MemMini Query Analyzer

자연어 쿼리를 구조화된 검색 파라미터로 변환.
"""

import re
from typing import Any, Dict, List, Optional, Protocol, cast


class LLMProvider(Protocol):
    """LLM 추상화 (선택적)

    Examples:
        >>> class MyLLM:
        ...     def generate(self, prompt: str) -> str:
        ...         return "..."
    """

    def generate(self, prompt: str, max_tokens: int = 200) -> str:
        """텍스트 생성"""
        ...


class QueryAnalyzer:
    """쿼리 분석기

    자연어 쿼리에서 검색 파라미터 추출.

    Examples:
        >>> analyzer = QueryAnalyzer()
        >>> result = analyzer.analyze("React 프로젝트 찾아줘. 실패한 건 제외하고")
        >>> result
        {
            'query': 'React 프로젝트',
            'positive': ['React', '프로젝트'],
            'negative': ['실패'],
            'filters': {}
        }
    """

    def __init__(self, llm: Optional[LLMProvider] = None):
        """QueryAnalyzer 초기화

        Args:
            llm: LLM 제공자 (None이면 rule-based만)
        """
        self.llm = llm

        # 한국어 불용어 (일반적인 조사, 접속사 등)
        self.stop_words = {
            "이",
            "그",
            "저",
            "것",
            "수",
            "등",
            "및",
            "또는",
            "하지만",
            "그러나",
            "그리고",
            "또한",
            "때문에",
            "위해",
            "대해",
            "관해",
            "통해",
            "따라",
            "의",
            "가",
            "이",
            "을",
            "를",
            "에",
            "에서",
            "로",
            "으로",
            "와",
            "과",
            "도",
            "만",
            "까지",
            "부터",
            "조차",
            "마저",
            "나",
            "너",
            "저",
            "우리",
            "그들",
            "이것",
            "그것",
            "저것",
            "여기",
            "거기",
            "저기",
            "이런",
            "그런",
            "저런",
            "어떤",
            "무슨",
            "어느",
            "몇",
            "하나",
            "둘",
            "셋",
            "있다",
            "없다",
            "되다",
            "하다",
            "좀",
            "더",
            "덜",
            "매우",
            "아주",
            "정말",
            "진짜",
            "너무",
            "참",
            "좀",
            "약간",
            "조금",
            "많이",
            "적게",
            "찾아줘",
            "찾아",
            "검색",
            "보여줘",
            "알려줘",
            "entries",
            "ones",
        }

        # 제외 의도를 나타내는 패턴
        self.exclude_markers = [
            r"제외",
            r"빼고",
            r"말고",
            r"아니",
            r"않은",
            r"없는",
            r"exclude",
            r"without",
            r"except",
            r"\bnot\b",
        ]

        # 제외 대상으로 자주 쓰이는 상태 키워드
        self.negative_roots = [
            r"실패",
            r"폐기",
            r"취소",
            r"보류",
            r"중단",
            r"거부",
            r"fail",
            r"failed",
            r"failure",
            r"discard",
            r"discarded",
            r"cancel",
            r"cancelled",
            r"canceled",
        ]
        self.negative_patterns = self.exclude_markers + self.negative_roots

    def analyze(self, query: str, use_llm: bool = False) -> Dict:
        """쿼리 분석

        Args:
            query: 자연어 쿼리
            use_llm: LLM 사용 여부 (False면 rule-based)

        Returns:
            분석 결과 딕셔너리
        """
        if use_llm and self.llm:
            return self._analyze_with_llm(query)
        else:
            return self._analyze_rule_based(query)

    def _analyze_rule_based(self, query: str) -> Dict:
        """Rule-based 쿼리 분석"""
        result = {
            "query": query,
            "positive": [],
            "negative": [],
            "filters": {},
        }

        if not query.strip():
            return result

        # 1. Negative 키워드와 검색 본문 분리
        negative_matches = []
        positive_clauses = []

        for clause in self._split_clauses(query):
            if self._has_exclude_intent(clause):
                negative_matches.extend(self._extract_negative_keywords(clause))
                cleaned_clause = self._remove_negative_phrase(clause)
                if cleaned_clause:
                    positive_clauses.append(cleaned_clause)
            else:
                positive_clauses.append(clause)

        cleaned_query = " ".join(positive_clauses).strip()
        if cleaned_query:
            result["query"] = cleaned_query

        # 2. Positive 키워드 추출
        # 명사, 고유명사 추출
        positive_words = re.findall(r"[가-힣a-zA-Z]+", cleaned_query)
        positive_keywords = [
            word
            for word in positive_words
            if (
                word not in self.stop_words
                and len(word) > 1
                and word not in negative_matches
            )
        ]

        # 3. 중복 제거
        result["positive"] = list(dict.fromkeys(positive_keywords))[:5]  # 상위 5개
        result["negative"] = list(dict.fromkeys(negative_matches))[:3]  # 상위 3개

        # 4. 필터 추출 (선택적)
        result["filters"] = self._extract_filters(query)

        return result

    def _split_clauses(self, query: str) -> List[str]:
        """문장 단위로 쿼리를 나눔."""
        return [
            clause.strip()
            for clause in re.split(r"[.!?。;\n]+", query)
            if clause.strip()
        ]

    def _has_exclude_intent(self, clause: str) -> bool:
        """구문에 제외 의도가 있는지 확인."""
        return any(
            re.search(pattern, clause, re.IGNORECASE)
            for pattern in self.exclude_markers
        )

    def _extract_negative_keywords(self, clause: str) -> List[str]:
        """제외 구문에서 실제 제외 키워드를 추출."""
        negative_keywords = []
        words = re.findall(r"[가-힣a-zA-Z]+", clause)

        for word in words:
            normalized = self._normalize_negative_word(word)
            if normalized and normalized not in negative_keywords:
                negative_keywords.append(normalized)

        if negative_keywords:
            return negative_keywords

        marker_match = self._first_marker_match(clause)
        if not marker_match:
            return []

        before_marker = clause[: marker_match.start()]
        for word in re.findall(r"[가-힣a-zA-Z]+", before_marker):
            if word not in self.stop_words and len(word) > 1:
                negative_keywords.append(word)

        return list(dict.fromkeys(negative_keywords))

    def _normalize_negative_word(self, word: str) -> Optional[str]:
        """활용형 키워드를 검색 가능한 기본 키워드로 정규화."""
        lowered = word.lower()

        for root in self.negative_roots:
            normalized_root = root.replace(r"\b", "")
            if normalized_root.lower() in lowered:
                if normalized_root in {"fail", "failure"}:
                    return "failed"
                return normalized_root

        return None

    def _remove_negative_phrase(self, clause: str) -> str:
        """제외 구문을 제거하고 남은 검색 본문을 반환."""
        lower_clause = clause.lower()
        root_positions = []

        for root in self.negative_roots:
            normalized_root = root.replace(r"\b", "").lower()
            pos = lower_clause.find(normalized_root)
            if pos >= 0:
                root_positions.append(pos)

        if root_positions:
            return clause[: min(root_positions)].strip(" ,")

        marker_match = self._first_marker_match(clause)
        if marker_match:
            return clause[marker_match.end() :].strip(" ,")

        return clause

    def _first_marker_match(self, clause: str) -> Optional[re.Match[str]]:
        """가장 앞에 나온 제외 marker match를 반환."""
        matches = [
            match
            for pattern in self.exclude_markers
            for match in [re.search(pattern, clause, re.IGNORECASE)]
            if match
        ]
        if not matches:
            return None
        return min(matches, key=lambda match: match.start())

    def _analyze_with_llm(self, query: str) -> Dict:
        """LLM 기반 쿼리 분석"""
        if self.llm is None:
            return self._analyze_rule_based(query)

        prompt = f"""다음 검색 쿼리를 분석하여 JSON으로 출력하세요.

쿼리: {query}

출력 형식:
{{
  "query": "정제된 검색 쿼리",
  "positive": ["반드시 포함할 키워드"],
  "negative": ["제외할 키워드"],
  "filters": {{"category": "...", "tags": [...]}}
}}

규칙:
- positive: 사용자가 찾고자 하는 핵심 키워드
- negative: "제외", "빼고", "말고", "실패" 등과 연관된 키워드
- filters: category, tags, priority 등 메타데이터 필터
- 각 리스트는 최대 5개까지

JSON만 출력:"""

        try:
            response = self.llm.generate(prompt, max_tokens=200)

            # JSON 파싱
            import json

            clean_text = response.replace("```json", "").replace("```", "").strip()
            start = clean_text.find("{")
            end = clean_text.rfind("}") + 1

            if start != -1 and end != -1:
                json_str = clean_text[start:end]
                data = json.loads(json_str)

                return {
                    "query": data.get("query", query),
                    "positive": data.get("positive", []),
                    "negative": data.get("negative", []),
                    "filters": data.get("filters", {}),
                }
        except Exception:
            # LLM 실패 시 fallback
            pass

        # Fallback to rule-based
        return self._analyze_rule_based(query)

    def _extract_filters(self, query: str) -> Dict:
        """쿼리에서 필터 추출 (간단한 패턴 매칭)"""
        filters = {}

        # Category 패턴: 일반 검색어가 아니라 명시적 필터 표현만 처리
        category_match = re.search(
            r"(?:category|카테고리|분류)\s*[:=]\s*([가-힣a-zA-Z0-9_-]+)",
            query,
            re.IGNORECASE,
        )
        if category_match:
            filters["category"] = category_match.group(1)

        # Priority 패턴
        if re.search(r"중요|긴급|우선순위", query, re.IGNORECASE):
            filters["priority"] = "high"

        # 날짜 패턴 (간단한 예시)
        date_match = re.search(r"(\d{4})-(\d{2})-(\d{2})", query)
        if date_match:
            filters["date"] = date_match.group(0)

        return filters


def extract_keywords(text: str, limit: int = 5) -> List[str]:
    """텍스트에서 키워드 추출 (유틸리티 함수)

    Args:
        text: 입력 텍스트
        limit: 최대 키워드 수

    Returns:
        키워드 리스트

    Examples:
        >>> extract_keywords("React 프로젝트 시작")
        ['React', '프로젝트', '시작']
    """
    analyzer = QueryAnalyzer()
    result = analyzer.analyze(text)
    positive = cast(List[Any], result.get("positive", []))
    return [str(keyword) for keyword in positive[:limit]]
