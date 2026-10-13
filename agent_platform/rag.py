"""本地、可复现的知识检索组件。

纯内存倒排索引 RAG，不依赖网络、向量数据库或外部 embedding 服务：
1. 启动时读取 knowledge/knowledge_base.md，按 ``## [source-id] 标题`` 解析章节并切块；
2. 对中文双字词 / 英文整词建立「词项 → 片段下标」倒排索引；
3. 查询时按词面重合度打分、过滤弱相关，取 top_k 个片段作为工具 observation。
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
import re


# 章节头格式：``## [source-id] 标题``，source-id 用于在回答中引用来源。
_SECTION_PATTERN = re.compile(r"^##\s+\[([a-z0-9][a-z0-9-]*)\]\s+(.+?)\s*$")
# 分词单元：连续的英文/数字算一个整词，连续中文先整段取出再切双字词。
_TOKEN_PATTERN = re.compile(r"[a-z0-9]+|[\u4e00-\u9fff]+", re.IGNORECASE)
# 切块时优先在这些句末标点处断开，避免把句子切成两半。
_SENTENCE_BOUNDARIES = "。！？；"


@dataclass(frozen=True)
class KnowledgeChunk:
    """知识库中可检索、可引用的最小文本片段。"""

    source_id: str
    title: str
    content: str


@dataclass(frozen=True)
class SearchResult:
    """一次检索命中的片段及其内部排序分数。"""

    chunk: KnowledgeChunk
    score: float


class KnowledgeBase:
    """启动时加载 Markdown 语料，并在内存中构建只读词项索引。"""

    def __init__(self, source_path: Path, *, chunk_size: int = 260, max_results: int = 3):
        """Fail Fast 构造：参数非法、语料缺失或解析为空都直接抛异常。"""
        if chunk_size < 80:
            raise ValueError("rag_chunk_size 不能小于 80 个字符。")
        if max_results < 1:
            raise ValueError("rag_top_k 必须至少为 1。")

        self.source_path = Path(source_path)
        self._max_results = max_results
        # 切块结果固化为 tuple，保证索引在运行期只读、可复现。
        self._chunks = tuple(self._load_chunks(chunk_size))
        if not self._chunks:
            raise ValueError(f"知识库没有可检索内容：{self.source_path}")
        self._term_index = self._build_term_index(self._chunks)

    @classmethod
    def from_default_file(cls, *, chunk_size: int = 260, max_results: int = 3) -> "KnowledgeBase":
        """读取项目内置语料，不依赖网络、数据库或外部 embedding 服务。"""
        source_path = Path(__file__).resolve().parent.parent / "knowledge" / "knowledge_base.md"
        return cls(source_path, chunk_size=chunk_size, max_results=max_results)

    @property
    def chunk_count(self) -> int:
        """返回启动时建立索引的片段数量，便于观察和验证。"""
        return len(self._chunks)

    def search(self, query: str, *, top_k: int = 3) -> list[SearchResult]:
        """按中文双字词/英文词的重合度检索，并过滤弱相关的候选片段。"""
        # 1. 查询分词；无有效词项时直接返回空，由上层决定提示未命中或凭知识回答。
        terms = set(_extract_terms(query))
        if not terms:
            return []

        # 2. 倒排命中计数：每命中一个词项，对应片段加 1 分。
        scores: Counter[int] = Counter()
        for term in terms:
            for chunk_index in self._term_index.get(term, ()):
                scores[chunk_index] += 1
        if not scores:
            return []

        # 3. 汇总打分：命中词数 + 标题命中加权（标题命中更能代表主题相关）。
        ranked: list[SearchResult] = []
        for chunk_index, matched_terms in scores.items():
            chunk = self._chunks[chunk_index]
            title_terms = set(_extract_terms(chunk.title))
            score = float(matched_terms) + 0.75 * len(terms & title_terms)
            ranked.append(SearchResult(chunk=chunk, score=score))

        # 4. 分数降序排序，按“最高分的一定比例”过滤弱相关后按 top_k 截断。
        ranked.sort(key=lambda item: (-item.score, item.chunk.source_id, item.chunk.title))
        minimum_score = max(1.0, ranked[0].score * 0.55)
        limit = max(1, min(int(top_k), self._max_results))
        return [item for item in ranked if item.score >= minimum_score][:limit]

    def _load_chunks(self, chunk_size: int) -> list[KnowledgeChunk]:
        """读取语料文件、解析章节，并把每节正文切成不超过 chunk_size 的片段。"""
        if not self.source_path.is_file():
            raise FileNotFoundError(f"知识库文件不存在：{self.source_path}")

        sections = _parse_sections(self.source_path.read_text(encoding="utf-8"))
        chunks: list[KnowledgeChunk] = []
        for source_id, title, content in sections:
            for part in _split_text(content, chunk_size):
                chunks.append(KnowledgeChunk(source_id=source_id, title=title, content=part))
        return chunks

    @staticmethod
    def _build_term_index(chunks: tuple[KnowledgeChunk, ...]) -> dict[str, tuple[int, ...]]:
        """为每个片段的 source_id、标题和正文建立「词项 → 片段下标」倒排索引。"""
        mutable_index: dict[str, list[int]] = defaultdict(list)
        for index, chunk in enumerate(chunks):
            searchable_text = f"{chunk.source_id} {chunk.title} {chunk.content}"
            # 同一词项在同一片段只记录一次，避免长文因重复词获得虚高分数。
            for term in set(_extract_terms(searchable_text)):
                mutable_index[term].append(index)
        return {term: tuple(indexes) for term, indexes in mutable_index.items()}


def _parse_sections(markdown: str) -> list[tuple[str, str, str]]:
    """解析 ``## [source-id] 标题`` 格式的受控 Markdown 语料。"""
    sections: list[tuple[str, str, str]] = []
    source_id: str | None = None
    title = ""
    lines: list[str] = []

    def append_current() -> None:
        if source_id is None:
            return
        content = _normalise_whitespace(" ".join(lines))
        if content:
            sections.append((source_id, title, content))

    # 逐行扫描的小型状态机：遇到新章节头就先归档上一节，再开始累积新一节；
    # 章节头之前的零散行（source_id 仍为 None）直接忽略。
    for line in markdown.splitlines():
        match = _SECTION_PATTERN.match(line)
        if match:
            append_current()
            source_id, title = match.groups()
            lines = []
        elif source_id is not None:
            lines.append(line)
    append_current()  # 文件末尾不会触发新章节头，需手动归档最后一节
    return sections


def _split_text(content: str, chunk_size: int) -> list[str]:
    """优先在句末切分，限制单个工具 observation 的文本长度。"""
    remaining = _normalise_whitespace(content)
    chunks: list[str] = []
    while remaining:
        if len(remaining) <= chunk_size:
            chunks.append(remaining)
            break

        window = remaining[:chunk_size]
        # 在窗口内找最靠后的句末边界；边界太靠前（不足半窗）则硬切，避免产生过短片段。
        boundary = max((window.rfind(marker) + 1 for marker in _SENTENCE_BOUNDARIES), default=0)
        cut_at = boundary if boundary >= chunk_size // 2 else chunk_size
        chunks.append(remaining[:cut_at].strip())
        remaining = remaining[cut_at:].lstrip()
    return chunks


def _extract_terms(text: str) -> list[str]:
    """将中文连续文本转为双字词，将英文与数字保留为完整词。"""
    terms: list[str] = []
    for token in _TOKEN_PATTERN.findall(text.lower()):
        if token[0].isascii():
            terms.append(token)  # 英文/数字整词保留
        elif len(token) == 1:
            terms.append(token)  # 单个汉字直接成词
        else:
            # 连续中文切为双字 bigram（如“西湖景区”→西湖/湖景/景区），兼顾召回与精度。
            terms.extend(token[index:index + 2] for index in range(len(token) - 1))
    return terms


def _normalise_whitespace(text: str) -> str:
    """把任意连续空白压缩为单个空格，保证切块与分词结果稳定。"""
    return re.sub(r"\s+", " ", text).strip()
