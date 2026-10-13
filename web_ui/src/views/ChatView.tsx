import { useEffect, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { api, ChatMessage, Conversation } from '../api'
import ConversationList from '../components/ConversationList'

// 展示用消息：在后端消息基础上附加本轮召回的长期记忆与“回复中”占位。
interface UiMessage extends ChatMessage {
  memoryContext?: string
  pending?: boolean
}

// 聊天主视图：左侧会话列表（新建/切换/删除），右侧消息流与输入框。
export default function ChatView() {
  const { conversationId } = useParams()
  const navigate = useNavigate()
  const [conversations, setConversations] = useState<Conversation[]>([])
  const [messages, setMessages] = useState<UiMessage[]>([])
  const [input, setInput] = useState('')
  const [sending, setSending] = useState(false)
  const bottomRef = useRef<HTMLDivElement>(null)
  // 跟踪当前会话：异步回包时比对，防止切换会话后迟到的响应污染新会话的消息流。
  const activeIdRef = useRef(conversationId)
  activeIdRef.current = conversationId

  // 首次进入：拉会话列表；一个都没有时自动建一个，保证开箱即可对话。
  useEffect(() => {
    void (async () => {
      let list = await api.listConversations()
      if (list.length === 0) {
        list = [await api.createConversation()]
      }
      setConversations(list)
      if (!conversationId || !list.some((item) => item.id === conversationId)) {
        navigate(`/c/${list[0].id}`, { replace: true })
      }
    })()
    // 仅挂载时执行一次；之后的会话切换完全由地址栏驱动。
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // 会话切换时加载该会话的短期历史（后端按 conversation_id 隔离）。
  useEffect(() => {
    if (!conversationId) {
      setMessages([])
      return
    }
    setMessages([])
    let cancelled = false
    void api.listMessages(conversationId).then((items) => {
      if (!cancelled) setMessages(items)
    })
    return () => {
      cancelled = true
    }
  }, [conversationId])

  // 新消息到达时滚动到底部。
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const createConversation = async () => {
    const created = await api.createConversation()
    setConversations((prev) => [...prev, created])
    navigate(`/c/${created.id}`)
  }

  const removeConversation = async (id: string) => {
    // 删除只清该会话的短期历史，用户长期记忆保留——提示语与后端语义保持一致。
    if (!window.confirm('删除该会话及其短期历史？（长期记忆会保留）')) return
    await api.deleteConversation(id)
    const next = conversations.filter((item) => item.id !== id)
    if (id !== conversationId) {
      setConversations(next)
      return
    }
    // 删掉的是当前会话：跳到剩余第一个；一个都不剩则新建空会话兜底。
    if (next.length > 0) {
      setConversations(next)
      navigate(`/c/${next[0].id}`, { replace: true })
    } else {
      const created = await api.createConversation()
      setConversations([created])
      navigate(`/c/${created.id}`, { replace: true })
    }
  }

  const sendMessage = async () => {
    const content = input.trim()
    if (!content || !conversationId || sending) return
    const targetId = conversationId
    setInput('')
    setSending(true)
    // 乐观渲染用户消息与“回复中”占位，拿到响应后替换占位。
    setMessages((prev) => [
      ...prev,
      { role: 'user', content },
      { role: 'assistant', content: '思考中…', pending: true },
    ])
    try {
      const result = await api.sendMessage(targetId, content)
      // 等待期间用户可能已切换会话：历史已写入后端，切回时自会加载，这里直接丢弃。
      if (activeIdRef.current !== targetId) return
      setMessages((prev) => [
        ...prev.slice(0, -1),
        { role: 'assistant', content: result.answer, memoryContext: result.memory_context },
      ])
    } catch (error) {
      if (activeIdRef.current !== targetId) return
      const reason = error instanceof Error ? error.message : String(error)
      setMessages((prev) => [...prev.slice(0, -1), { role: 'assistant', content: `请求失败：${reason}` }])
    } finally {
      setSending(false)
    }
  }

  return (
    <div className="layout">
      <aside className="sidebar">
        <div className="sidebar-header">
          <span>会话</span>
          <button onClick={() => void createConversation()}>＋ 新建会话</button>
        </div>
        <ConversationList
          conversations={conversations}
          activeId={conversationId}
          onSelect={(id) => navigate(`/c/${id}`)}
          onRemove={(id) => void removeConversation(id)}
        />
        <div className="sidebar-footer">
          长期记忆跨会话共享：在任意会话里说「请记住…」，其他会话也能召回。
        </div>
      </aside>
      <main className="chat">
        <div className="messages">
          {messages.map((message, index) => (
            <div
              key={index}
              className={`bubble ${message.role}${message.pending ? ' pending' : ''}`}
            >
              <div>{message.content}</div>
              {message.memoryContext && (
                <details className="memory-context">
                  <summary>本轮召回的长期记忆</summary>
                  <pre>{message.memoryContext}</pre>
                </details>
              )}
            </div>
          ))}
          <div ref={bottomRef} />
        </div>
        <div className="composer">
          <textarea
            value={input}
            rows={2}
            placeholder="输入消息，Enter 发送（Shift+Enter 换行）"
            onChange={(event) => setInput(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === 'Enter' && !event.shiftKey) {
                event.preventDefault()
                void sendMessage()
              }
            }}
          />
          <button
            disabled={sending || !input.trim() || !conversationId}
            onClick={() => void sendMessage()}
          >
            发送
          </button>
        </div>
      </main>
    </div>
  )
}
