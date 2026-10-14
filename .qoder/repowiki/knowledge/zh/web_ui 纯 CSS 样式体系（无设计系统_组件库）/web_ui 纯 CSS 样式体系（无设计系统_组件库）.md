---
kind: frontend_style
name: web_ui 纯 CSS 样式体系（无设计系统/组件库）
category: frontend_style
scope:
    - '**'
source_files:
    - web_ui/src/styles.css
    - web_ui/package.json
    - web_ui/vite.config.ts
    - web_ui/src/components/ConversationList.tsx
    - web_ui/src/views/ChatView.tsx
---

## 1. 使用的系统与工具

- 构建与开发：Vite 5 + `@vitejs/plugin-react`，TypeScript 5.6。
- UI 框架：React 18.3 + react-router-dom 6.26，仅用于路由与组件结构，**不引入任何 UI 组件库**（如 Ant Design、MUI、Tailwind 等）。
- 样式方案：**纯 CSS**，所有样式集中在单一文件 `web_ui/src/styles.css`，通过 `main.tsx` 全局引入。没有 SCSS、CSS Modules、styled-components、Tailwind 或任何 CSS-in-JS 方案。
- 主题/设计令牌：不存在独立的设计令牌文件或主题配置；颜色、字号、间距等以硬编码字面量形式直接写在 CSS 中。

## 2. 关键文件

- `web_ui/src/styles.css` — 唯一的全局样式源，定义了两栏布局、侧边栏、消息气泡、输入区等全部视觉样式。
- `web_ui/package.json` — 声明了 React/Vite/TS 依赖，未包含任何样式相关依赖。
- `web_ui/vite.config.ts` — 仅配置 React 插件与 `/api` 代理到 FastAPI，不包含 PostCSS/Tailwind 等样式管线。
- `web_ui/src/components/ConversationList.tsx`、`web_ui/src/views/ChatView.tsx` — 使用 BEM 风格类名（`.sidebar`、`.conversation-list`、`.bubble.user`、`.composer` 等）引用 `styles.css`。

## 3. 架构与约定

- **单文件全局样式**：所有样式写在一个 `.css` 文件中，由入口 `main.tsx` 一次性 import，组件内不导入局部样式。
- **BEM 风格命名**：类名采用 `<block>.<element>.<modifier>` 的语义化命名，例如 `.conversation-list li.active`、`.bubble.user`、`.bubble.assistant`、`.composer textarea`、`.sidebar-header button`。
- **两栏布局**：根容器 `.layout` 使用 `display: flex; height: 100vh`，左侧 `.sidebar` 固定宽度 `260px`，右侧 `.chat` 用 `flex: 1` 自适应填充。
- **配色约定**：
  - 主色蓝：`#3b82f6`（按钮、用户气泡），hover 态为 `#2563eb`。
  - 侧栏背景：`#20242b`，文字 `#e6e8eb` / `#c9cdd4` / `#8a8f99`。
  - 页面背景：`#f5f6f7`，正文色 `#1f2329`。
  - 边框/分割线：`#e5e7eb`，禁用态灰：`#9ca3af`。
- **字体栈**：`-apple-system, "PingFang SC", "Helvetica Neue", "Microsoft YaHei", sans-serif`，优先系统字体并回退到苹方/雅黑。
- **响应式策略**：未发现媒体查询或断点；布局基于 Flexbox 自适应宽度，但未见移动端适配代码。
- **生产托管**：`vite.config.ts` 注释说明生产模式由 FastAPI 直接托管 `dist/` 产物，开发时通过 Vite proxy 将 `/api` 转发到本地 8000 端口的 FastAPI。

## 4. 约定与约束

- **样式组织**：当前仓库只有一份全局 CSS 文件，组件通过 className 引用，没有按组件拆分样式文件的约定（因为尚未出现该需求）。
- **无设计系统**：没有 `tailwind.config.*`、`theme.js`、CSS 变量集中管理或组件库集成；颜色、圆角、阴影等值在 CSS 中以字面量重复出现（如圆角 `6px`、`8px`、`12px` 多处硬编码）。
- **无构建期样式校验**：`package.json` 和 `tsconfig.json` 中未发现 ESLint/Prettier/Sass/Lint 等样式质量工具的配置，因此样式规范是约定而非强制约束。
- **类名命名**：从现有代码看，BEM 风格类名是实际采用的约定（`.sidebar-*`、`.conversation-list-*`、`.bubble.*`、`.composer-*`），但未被 lint 规则强制。
- **浏览器兼容**：未配置 Autoprefixer 或 polyfill，默认使用现代 CSS（Flexbox、CSS Grid 未使用）。