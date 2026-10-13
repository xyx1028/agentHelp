import { Conversation } from '../api'

interface Props {
  conversations: Conversation[]
  activeId?: string
  onSelect: (id: string) => void
  onRemove: (id: string) => void
}

// 侧栏会话列表：点击切换会话，悬停出现删除按钮。
export default function ConversationList({ conversations, activeId, onSelect, onRemove }: Props) {
  return (
    <ul className="conversation-list">
      {conversations.map((item) => (
        <li
          key={item.id}
          className={item.id === activeId ? 'active' : ''}
          onClick={() => onSelect(item.id)}
        >
          <span className="title">{item.title}</span>
          <button
            className="remove"
            title="删除会话"
            onClick={(event) => {
              // 阻止冒泡，避免触发整行的切换会话。
              event.stopPropagation()
              onRemove(item.id)
            }}
          >
            ×
          </button>
        </li>
      ))}
    </ul>
  )
}
