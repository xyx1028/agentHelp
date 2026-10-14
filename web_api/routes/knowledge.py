"""知识库管理路由：Web 端文档上传与索引维护的唯一入口。

管理操作直接作用于 serve 进程内共享的 LlamaIndexKnowledgeBase 实例——
与 Agent 检索所用的是同一个对象，因此上传/重建后新问答立即生效。
mock 或词法后端不具备管理能力（每次启动全量加载，无索引维护概念），
相关端点统一返回 409，前端据 stats 的 manageable 标识禁用入口。
"""

from pathlib import Path
import tempfile

from fastapi import APIRouter, File, HTTPException, UploadFile

from agent_platform.rag import LlamaIndexKnowledgeBase

from ..schemas import IngestDocumentsOut, KnowledgeStatsOut, ReindexOut


def build_knowledge_router(knowledge_base: object | None) -> APIRouter:
    """构造知识库管理路由；knowledge_base 非向量实例时管理端点返回 409。"""

    router = APIRouter(prefix="/api/knowledge", tags=["knowledge"])

    def require_vector() -> LlamaIndexKnowledgeBase:
        """仅向量后端具备 ingest/rebuild 能力；其余装配（mock）如实拒绝。"""
        if not isinstance(knowledge_base, LlamaIndexKnowledgeBase):
            raise HTTPException(status_code=409, detail="当前为 mock 或词法后端，知识库管理不可用。")
        return knowledge_base

    @router.get("/stats")
    def stats() -> KnowledgeStatsOut:
        """返回可管理标识与片段总数；任何装配下都可用，供前端决定是否开放入口。"""
        vector = knowledge_base if isinstance(knowledge_base, LlamaIndexKnowledgeBase) else None
        return KnowledgeStatsOut(
            manageable=vector is not None,
            chunk_count=vector.chunk_count if vector is not None else 0,
        )

    @router.post("/documents", status_code=201)
    def upload_documents(files: list[UploadFile] = File(...)) -> IngestDocumentsOut:
        """把上传文件灌入向量库；逐文件处理，单个失败不影响其余，明细随响应返回。"""
        base = require_vector()
        if not files:
            raise HTTPException(status_code=400, detail="没有收到文件。")

        added = 0
        ingested: list[str] = []
        errors: dict[str, str] = {}
        for upload in files:
            # 只取文件名最后一段防路径穿越；临时目录中保留原名，
            # 因为 ingest 以文件名作为 [source:...] 来源标识。
            original_name = Path(upload.filename or "upload").name
            try:
                with tempfile.TemporaryDirectory() as tmp_dir:
                    tmp_path = Path(tmp_dir) / original_name
                    tmp_path.write_bytes(upload.file.read())
                    added += base.ingest([tmp_path])
                ingested.append(original_name)
            except (ValueError, FileNotFoundError) as error:
                errors[original_name] = str(error)
        if not ingested and errors:
            # 全部失败时整体按 400 处理，明细带回去便于前端一次性展示。
            raise HTTPException(status_code=400, detail=f"全部文件灌入失败：{errors}")
        return IngestDocumentsOut(
            ingested_files=ingested,
            added_chunks=added,
            chunk_count=base.chunk_count,
            errors=errors,
        )

    @router.post("/reindex")
    def reindex() -> ReindexOut:
        """清空并全量重建索引；与 Agent 检索共用同一实例，重建后立即可用。"""
        base = require_vector()
        return ReindexOut(chunk_count=base.rebuild())

    return router
