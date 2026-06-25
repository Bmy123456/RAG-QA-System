# RAG 智能问答系统

基于 RAG（检索增强生成）的多用户私有文档智能问答系统。上传文档，建立知识库，用自然语言提问，获得带来源标注的精准回答。

## 功能特性

- **多格式文档支持**：PDF、Word、Excel、PPT、图片（OCR）、网页、邮件
- **多用户隔离**：JWT 认证（Access Token + Refresh Token），RBAC 角色权限（普通用户/管理员）
- **智能检索**：向量相似度 + BM25 稀疏检索 + RRF 融合，LLM 重排序，两阶段保证答案质量
- **流式对话**：SSE 实时输出，逐 token 渲染，类 ChatGPT 的对话体验
- **来源引用**：回答标注文档名、页码，可追溯到原文
- **知识库权限**：私有知识库仅自己可见，支持公共知识库所有用户可读
- **反馈系统**：用户可对回答标记有用/无用/纠正，管理员可审核和导出
- **离线评估**：支持检索质量（Precision@K、Recall@K、MRR、MAP）和生成质量（忠实度、BLEU）评估

## 快速开始

### 1. 环境准备

- Python 3.10+
- Node.js 18+（前端构建）
- LLM API Key（MiMo / DeepSeek / OpenAI 等）

### 2. 配置环境变量

```bash
cp .env.example .env
# 编辑 .env，填入你的密钥
```

`.env` 文件内容：

```env
SECRET_KEY=your-secret-key-here
MIMO_API_KEY=sk-your-api-key-here
```

### 3. 启动后端

```bash
pip install -r requirements.txt
uvicorn backend.main:app --reload --port 8000
```

### 4. 启动前端

```bash
cd frontend
pnpm install
pnpm dev
```

浏览器访问 `http://localhost:5173`，注册账号后即可使用。

## 生产部署

### Docker

```bash
docker-compose up -d
```

Docker 构建会自动完成前端编译并托管静态文件，访问 `http://localhost:8000`。

### 手动部署

```bash
# 构建前端
cd frontend
pnpm install
pnpm build
cd ..

# 启动后端（自动托管 frontend/dist/ 静态文件）
uvicorn backend.main:app --host 0.0.0.0 --port 8000
```

## 使用流程

1. **注册/登录** → 创建账号
2. **创建知识库** → 输入名称，可设置为公共知识库
3. **上传文档** → 拖拽或点击上传，等待后台解析完成
4. **开始对话** → 选择知识库，输入问题，支持多轮对话和会话切换
5. **查看反馈** → 对回答提交反馈，管理员可审核和导出

## 项目结构

```
├── backend/
│   ├── api/            # API 路由 (auth, kb, chat, evaluation, admin)
│   ├── core/           # RAG 引擎 (检索, 重排序, 生成, 对话管理, 嵌入)
│   ├── db/             # 数据库引擎 + CRUD 操作
│   ├── models/         # SQLAlchemy ORM + Pydantic 模型
│   ├── config/         # 配置管理 (环境变量)
│   ├── utils/          # 文档解析器 + 文本分块器
│   └── evaluation/     # 离线 RAG 质量评估
├── frontend/           # React + TypeScript + Vite + Ant Design
│   ├── src/api/        # API 层 (axios + JWT 拦截器)
│   ├── src/stores/     # zustand 状态管理
│   ├── src/pages/      # 页面组件 (对话, 知识库, 反馈, 评估, 监控)
│   └── src/components/ # 通用组件 (布局, 会话列表, 反馈按钮)
└── data/               # 持久化数据 (gitignore)
```

## 技术栈

| 层 | 选型 |
|----|------|
| 后端框架 | FastAPI |
| 数据库 | SQLite + SQLAlchemy |
| 向量数据库 | ChromaDB |
| LLM | MiMo / DeepSeek / OpenAI（兼容 OpenAI 协议） |
| 嵌入模型 | MiMo / 通义 / 本地 sentence-transformers |
| 前端框架 | React 19 + TypeScript |
| 前端构建 | Vite |
| UI 组件库 | Ant Design 5 |
| 状态管理 | zustand |
| 认证 | JWT (python-jose + bcrypt) |

## API 文档

启动后访问 `http://localhost:8000/docs` 查看自动生成的 Swagger API 文档。
