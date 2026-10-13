// 与 FastAPI 后端交互的全部 HTTP 调用；组件不直接 fetch，接口变更只改本文件。

export interface Conversation {
  id: string
  title: string
}

export interface ChatMessage {
  role: 'user' | 'assistant'
  content: string
}

export interface SendMessageResult {
  answer: string
  memory_context: string
}

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, {
    headers: { 'Content-Type': 'application/json' },
    ...init,
  })
  if (!response.ok) {
    throw new Error(`${response.status} ${await response.text()}`)
  }
  // 204 No Content 没有响应体，直接返回 undefined。
  return (response.status === 204 ? undefined : await response.json()) as T
}

export const api = {
  listConversations: () => request<Conversation[]>('/api/conversations'),

  createConversation: () =>
    request<Conversation>('/api/conversations', { method: 'POST', body: '{}' }),

  deleteConversation: (id: string) =>
    request<void>(`/api/conversations/${id}`, { method: 'DELETE' }),

  listMessages: (conversationId: string) =>
    request<ChatMessage[]>(`/api/conversations/${conversationId}/messages`),

  sendMessage: (conversationId: string, content: string) =>
    request<SendMessageResult>(`/api/conversations/${conversationId}/messages`, {
      method: 'POST',
      body: JSON.stringify({ content }),
    }),
}
