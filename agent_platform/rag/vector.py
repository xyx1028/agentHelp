"""向量后端：LlamaIndex + Chroma 的本地语义检索实现，真实模式的默认后端。

索引生命周期（见 LlamaIndexKnowledgeBase.__init__）：
1. 打开 rag_persist_dir 下的 Chroma 嵌入式集合（本地文件，无独立服务进程）；
2. 集合为空时从 rag_knowledge_dir 全量灌入内置语料并构建索引（此时才调用 embedding）；
3. 集合非空则直接复用已持久化的向量，启动零 embedding 调用。
embedding 提供方可切换：fastembed（本地免费，首次运行自动下载开源模型）或
openai（OpenAI 兼容 API，机密由入口经构造函数注入而非读取环境变量）。
内置受控语料（``## [source-id] 标题``）复用词法后端的 parse_sections 解析，
保证 [source:...] 引用契约在两个后端间一致。
"""

from __future__ import annotations

from pathlib import Path
import re
import shutil
import threading
from typing import Any

from ..config import AgentSettings
from .lexical import parse_sections
from .models import KnowledgeChunk, SearchResult

# Chroma 集合名；单一知识库场景下固定即可。
_COLLECTION_NAME = "knowledge"
# --ingest 与 knowledge/ 目录自动灌入支持的文件格式（PDF/Word 依赖 pypdf、docx2txt 解析）。
_SUPPORTED_EXTENSIONS = (".md", ".txt", ".pdf", ".docx")
# 内置受控语料文件名：该文件按章节解析保留 [source-id]，目录里其余文件按整体读取。
_CONTROLLED_CORPUS_NAME = "knowledge_base.md"


class LlamaIndexKnowledgeBase:
    """基于 LlamaIndex 向量索引的检索后端；构造时打开索引，为空则自动全量构建。"""

    def __init__(
        self,
        settings: AgentSettings,
        *,
        embedding_api_key: str | None = None,
        embedding_base_url: str | None = None,
        force_rebuild: bool = False,
    ):
        """Fail Fast 构造：依赖缺失、语料为空、embedding 配置不全都直接抛异常。

        force_rebuild=True 时先删除已有集合再重建（服务 --reindex 场景）；
        embedding 机密经参数注入，保持配置流向显式、可打印的 AgentSettings 不含机密。
        """
        # llama-index / chromadb 体量大且评测走词法后端不需要，故惰性导入；
        # 缺失时把原生 ImportError 转成可操作的指引而非堆栈。
        try:
            from llama_index.core.node_parser import SentenceSplitter
        except ImportError as error:
            raise RuntimeError(
                "向量后端缺少依赖，请先执行 pip install -r requirements.txt；"
                "或临时改用离线词法后端（RAG_BACKEND=lexical）。"
            ) from error

        self._settings = settings
        self._embed_model = _build_embed_model(
            settings,
            api_key=embedding_api_key,
            base_url=embedding_base_url,
        )
        # 切块在索引构建时完成；ingest 追加时复用同一 splitter，保证全库块尺寸一致。
        self._splitter = SentenceSplitter(
            chunk_size=settings.rag_chunk_size,
            chunk_overlap=max(20, settings.rag_chunk_size // 6),  # 约 15% 重叠，缓解边界语义截断
        )
        self._max_results = settings.rag_top_k
        self._min_score = settings.rag_min_score
        # 管理操作（ingest/rebuild）与检索互斥：Web 端与 Agent 共享同一实例，
        # 避免重建过程中检索读到半个索引。
        self._lock = threading.RLock()
        self._client = None
        self._open(force_rebuild=force_rebuild)

    def _open(self, *, force_rebuild: bool) -> None:
        """打开（或重建）持久化索引；集合为空时自动从语料目录全量构建。

        rebuild() 与构造共用本方法：先释放旧 Chroma 连接再按需物理清空目录，
        重建后 self._index 指向全新集合，而实例引用对持有方（Agent 工具）不变。
        """
        # 依赖在首次构造时已验证存在；此处重复导入走解释器缓存，代价为零。
        import chromadb
        from llama_index.core import StorageContext, VectorStoreIndex
        from llama_index.vector_stores.chroma import ChromaVectorStore

        with self._lock:
            if self._client is not None:
                # 重建前释放旧连接：否则 rmtree 后旧句柄继续写已删除的 inode，产生幽灵数据。
                try:
                    self._client.close()
                except Exception:
                    pass  # 关闭失败不阻断重建；进程退出时资源自会回收

            persist_dir = Path(self._settings.rag_persist_dir)
            if force_rebuild and persist_dir.exists():
                # 物理清空整个索引目录：Chroma 的 delete_collection 只做逻辑删除，
                # 会残留 HNSW segment 目录，每 reindex 一次就多一份孤儿文件。
                # 防误删：只对确为 Chroma 持久化产物的目录下手，配置指错目录时拒绝执行。
                if (persist_dir / "chroma.sqlite3").exists() or not any(persist_dir.iterdir()):
                    shutil.rmtree(persist_dir)
                else:
                    raise ValueError(
                        f"rag_persist_dir 指向的目录不像 Chroma 索引目录，拒绝清空：{persist_dir}"
                    )
            persist_dir.mkdir(parents=True, exist_ok=True)
            self._client = chromadb.PersistentClient(path=str(persist_dir))
            # 余弦空间与 bge 系归一化向量匹配，相关性排序更稳定。
            self._collection = self._client.get_or_create_collection(
                _COLLECTION_NAME,
                metadata={"hnsw:space": "cosine"},
            )
            vector_store = ChromaVectorStore(chroma_collection=self._collection)
            storage_context = StorageContext.from_defaults(vector_store=vector_store)

            if self._collection.count() == 0:
                documents = _load_knowledge_documents(Path(self._settings.rag_knowledge_dir))
                if not documents:
                    raise ValueError(
                        f"知识库目录没有可索引的文档：{Path(self._settings.rag_knowledge_dir).resolve()}"
                    )
                self._index = VectorStoreIndex.from_documents(
                    documents,
                    storage_context=storage_context,
                    transformations=[self._splitter],
                    embed_model=self._embed_model,
                )
            else:
                # 复用已持久化的向量：检索直接打到 Chroma，无需 docstore 即可恢复索引。
                self._index = VectorStoreIndex.from_vector_store(vector_store, embed_model=self._embed_model)

    def rebuild(self) -> int:
        """清空并全量重建索引，返回重建后的片段总数。

        Web 管理端与 CLI reindex 共用；原地重建内部状态而实例引用不变，
        Agent 持有的检索工具无需任何处理即可在重建后继续工作。
        注意：重建只覆盖 knowledge/ 目录语料，此前 ingest 的外部文档需重新灌入。
        """
        self._open(force_rebuild=True)
        return self.chunk_count

    @property
    def chunk_count(self) -> int:
        """Chroma 集合中已持久化的片段总数。"""
        return self._collection.count()

    def search(self, query: str, *, top_k: int = 3) -> list[SearchResult]:
        """按向量相似度检索 top_k 片段；空查询直接返回空，由上层提示"资料不足"。"""
        if not query.strip():
            return []
        limit = max(1, min(int(top_k), self._max_results))
        with self._lock:
            # 与 ingest/rebuild 互斥，避免读到重建进行中的半个索引。
            nodes = self._index.as_retriever(similarity_top_k=limit).retrieve(query)
        results: list[SearchResult] = []
        for node in nodes:
            metadata = node.node.metadata
            # LlamaIndex 的 ChromaVectorStore 以 exp(-距离) 把余弦距离转为相似度
            # （越大越相关）；低于阈值视为未命中，与词法后端的弱相关过滤对齐——
            # 模型收到空结果才会如实说明资料不足而非硬答。
            if node.score is not None and node.score < self._min_score:
                continue
            results.append(
                SearchResult(
                    chunk=KnowledgeChunk(
                        source_id=str(metadata.get("source_id", "unknown")),
                        title=str(metadata.get("title", "")),
                        content=node.node.get_content(),
                    ),
                    # score 为 exp(-余弦距离) 的相似度（0~1，越大越相关），仅作观测。
                    score=float(node.score) if node.score is not None else 0.0,
                )
            )
        return results

    def ingest(self, paths: list[Path]) -> int:
        """把外部文档（MD/TXT/PDF/DOCX）切块追加进索引，返回新增片段数。

        同一文件重复灌入会产生重复片段；需要刷新时请用 --reindex 全量重建，
        避免为去重引入文档指纹簿记（现阶段没有按文档删除的需求）。
        """
        files = [Path(path) for path in paths]
        missing = [str(path) for path in files if not path.is_file()]
        if missing:
            raise FileNotFoundError(f"待灌入文件不存在：{', '.join(missing)}")
        unsupported = [path.name for path in files if path.suffix.lower() not in _SUPPORTED_EXTENSIONS]
        if unsupported:
            raise ValueError(
                f"暂不支持灌入该格式：{', '.join(unsupported)}（支持 {', '.join(_SUPPORTED_EXTENSIONS)}）"
            )

        documents = _read_external_documents(files)
        nodes = self._splitter.get_nodes_from_documents(documents)
        with self._lock:
            # 与检索/重建互斥；解析与切块在锁外完成，尽量缩短持锁时间。
            self._index.insert_nodes(nodes)
        return len(nodes)


def _build_embed_model(
    settings: AgentSettings,
    *,
    api_key: str | None,
    base_url: str | None,
) -> Any:
    """按 provider 装配 embedding 模型；各实现惰性导入，避免互相牵连依赖。"""
    provider = settings.rag_embedding_provider
    if provider == "fastembed":
        # 本地免费方案：首次运行自动从 HuggingFace 下载模型到用户缓存目录，
        # 之后离线可用；网络受限时设 HF_ENDPOINT=https://hf-mirror.com 走镜像。
        from llama_index.embeddings.fastembed import FastEmbedEmbedding

        return FastEmbedEmbedding(model_name=settings.rag_embedding_model)
    if provider == "openai":
        # OpenAI 兼容 API（含各类转发/国产服务）；注意 DeepSeek 没有 embedding 接口。
        from llama_index.embeddings.openai import OpenAIEmbedding

        if not api_key:
            raise ValueError("RAG_EMBEDDING_PROVIDER=openai 需要在 .env 中配置 EMBEDDING_API_KEY。")
        return OpenAIEmbedding(
            model=settings.rag_embedding_model,
            api_key=api_key,
            api_base=base_url,  # None 时走 SDK 默认官方地址
        )
    # config 已对枚举 Fail Fast 校验，此处为防御性兜底。
    raise ValueError(f"未知 embedding 提供方：{provider}")


def _load_knowledge_documents(knowledge_dir: Path) -> list[Any]:
    """读取内置语料目录，返回待索引的 LlamaIndex Document 列表。

    受控 knowledge_base.md 按章节解析（保住 [source-id] 引用契约）；
    目录中其余支持格式的文件按整体读取，以文件名作为来源标识。
    """
    from llama_index.core import Document

    documents: list[Any] = []
    controlled_file = knowledge_dir / _CONTROLLED_CORPUS_NAME
    if controlled_file.is_file():
        for source_id, title, content in parse_sections(controlled_file.read_text(encoding="utf-8")):
            # 标题并入正文：切块与 embedding 都以完整语义单元进行，标题仍单独入 metadata。
            documents.append(
                Document(
                    text=f"{title}\n{content}",
                    metadata={"source_id": source_id, "title": title},
                )
            )
    external_files = [
        path
        for path in sorted(knowledge_dir.rglob("*"))
        if path.is_file()
        and path.suffix.lower() in _SUPPORTED_EXTENSIONS
        and path.name != _CONTROLLED_CORPUS_NAME
    ]
    documents.extend(_read_external_documents(external_files))
    return documents


def _read_external_documents(files: list[Path]) -> list[Any]:
    """用 SimpleDirectoryReader 解析外部文件，并把来源标识规范化为 [source:文件名-slug]。"""
    if not files:
        return []
    from llama_index.core import SimpleDirectoryReader

    documents = SimpleDirectoryReader(input_files=[str(path) for path in files]).load_data()
    for document in documents:
        file_stem = Path(str(document.metadata.get("file_name", "unknown"))).stem
        document.metadata["source_id"] = _slugify(file_stem)
        document.metadata.setdefault("title", file_stem)
    return documents


def _slugify(text: str) -> str:
    """把文件名规整为稳定的来源标识：空白转连字符并小写，保留中英文与数字。"""
    slug = re.sub(r"\s+", "-", text.strip().lower())
    return slug or "unknown"
