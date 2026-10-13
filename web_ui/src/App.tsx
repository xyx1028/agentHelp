import { Outlet } from 'react-router-dom'

// 根布局：当前只是路由出口；以后加全局导航栏、登录态时写在这里。
export default function App() {
  return <Outlet />
}
