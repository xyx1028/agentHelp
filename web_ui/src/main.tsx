import React from 'react'
import ReactDOM from 'react-dom/client'
import { createBrowserRouter, RouterProvider } from 'react-router-dom'
import App from './App'
import ChatView from './views/ChatView'
import './styles.css'

// 路由骨架：当前只有聊天视图，/c/:conversationId 直链到指定会话；
// 以后新增页面时在此追加路由即可。
const router = createBrowserRouter([
  {
    path: '/',
    element: <App />,
    children: [
      { path: '', element: <ChatView /> },
      { path: 'c/:conversationId', element: <ChatView /> },
    ],
  },
])

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <RouterProvider router={router} />
  </React.StrictMode>,
)
