import { useCallback, useEffect, useRef, useState } from 'react'
import { api, KnowledgeStats } from '../api'

// 侧栏知识库管理面板：展示索引规模，提供文档上传与索引重建入口。
// mock 后端不具备管理能力时整体降级为说明文案（与后端 stats.manageable 对齐）。
export default function KnowledgePanel() {
  const [stats, setStats] = useState<KnowledgeStats | null>(null)
  const [busy, setBusy] = useState<'upload' | 'reindex' | null>(null)
  const [feedback, setFeedback] = useState('')
  const fileInputRef = useRef<HTMLInputElement>(null)

  const refresh = useCallback(async () => {
    try {
      setStats(await api.knowledgeStats())
    } catch {
      // 服务未就绪时静默降级，面板显示占位而非报错刷屏。
      setStats(null)
    }
  }, [])

  useEffect(() => {
    void refresh()
  }, [refresh])

  const upload = async (files: FileList | null) => {
    if (!files || files.length === 0) return
    setBusy('upload')
    setFeedback('')
    try {
      const result = await api.uploadDocuments(files)
      const failedNames = Object.keys(result.errors)
      const summary = `已灌入 ${result.ingested_files.length} 个文件、新增 ${result.added_chunks} 个片段。`
      // 部分文件失败不算整体失败，但失败明细要如实告知。
      setFeedback(
        failedNames.length > 0 ? `${summary}失败：${failedNames.join('、')}` : summary,
      )
      await refresh()
    } catch (error) {
      setFeedback(`上传失败：${error instanceof Error ? error.message : String(error)}`)
    } finally {
      setBusy(null)
      // 重置 input 的值，允许连续两次选择同一文件也能触发 change。
      if (fileInputRef.current) fileInputRef.current.value = ''
    }
  }

  const reindex = async () => {
    // 提示语义与后端 rebuild 一致：只保留 knowledge/ 目录语料，已上传文档需重新灌入。
    if (!window.confirm('清空并按 knowledge/ 目录全量重建索引？此前上传的文档需要重新灌入。')) return
    setBusy('reindex')
    setFeedback('')
    try {
      const result = await api.reindexKnowledge()
      setFeedback(`重建完成，当前共 ${result.chunk_count} 个片段。`)
      await refresh()
    } catch (error) {
      setFeedback(`重建失败：${error instanceof Error ? error.message : String(error)}`)
    } finally {
      setBusy(null)
    }
  }

  const manageable = stats?.manageable ?? false
  return (
    <section className="knowledge-panel">
      <div className="knowledge-header">
        <span>知识库</span>
        <span className="knowledge-count">{stats ? `${stats.chunk_count} 片段` : '…'}</span>
      </div>
      {manageable ? (
        <>
          <div className="knowledge-actions">
            <button disabled={busy !== null} onClick={() => fileInputRef.current?.click()}>
              {busy === 'upload' ? '上传中…' : '上传资料'}
            </button>
            <button disabled={busy !== null} onClick={() => void reindex()}>
              {busy === 'reindex' ? '重建中…' : '重建索引'}
            </button>
          </div>
          <input
            ref={fileInputRef}
            type="file"
            multiple
            accept=".md,.txt,.pdf,.docx"
            hidden
            onChange={(event) => void upload(event.target.files)}
          />
          <div className="knowledge-hint">支持 MD / TXT / PDF / Word，上传后即可提问。</div>
          {feedback && <div className="knowledge-feedback">{feedback}</div>}
        </>
      ) : (
        <div className="knowledge-hint">当前为 mock 模式，知识库管理不可用；上传与重建需真实模式。</div>
      )}
    </section>
  )
}
