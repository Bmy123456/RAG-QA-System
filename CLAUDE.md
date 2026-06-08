# CLAUDE.md

本文件为 Claude Code (claude.ai/code) 在此仓库中工作时提供指引。

## 项目概述

多用户 RAG 智能问答系统。用户上传文档（PDF/Word/Excel/PPT/图片/网页/邮件），系统解析后建立向量索引，通过 LLM 回答问题并标注来源出处。

## 技术栈

- **后端**: FastAPI + SQLAlchemy (SQLite) + ChromaDB
- **前端**: Vue 3 + Vite + Pinia + Vue Router
- **LLM**: DeepSeek API（兼容 OpenAI 协议）
- **Embedding**: DeepSeek Embedding API
- **重排序**: 基于 DeepSeek 的 prompt 评分（非本地 BGE 模型）

## 常用命令

```bash
# 后端
pip install -r requirements.txt
uvicorn app.main:app --reload              # 开发模式，端口 8000

# 前端
cd frontend && npm install && npm run dev   # 开发模式，端口 5173（代理 /api 到 :8000）
cd frontend && npm run build                # 生产构建 → frontend/dist/

# 生产部署（单端口）
cd frontend && npm run build && uvicorn app.main:app --host 0.0.0.0 --port 8000

# Docker
docker-compose up -d
```

## 环境变量

启动前必须设置: `SECRET_KEY`、`DEEPSEEK_API_KEY`。参考 `.env.example`。

## 架构

项目采用**模块化单体**架构，运行在单个 FastAPI 进程中。

**请求链路**: API 路由 → 服务层 → RAG 引擎 / 存储层

- `app/api/` — 仅处理 HTTP 请求/响应，不含业务逻辑，各路由注册在 `/api/...`
- `app/services/` — 业务编排：auth_service（JWT）、kb_service、document_service、chat_service
- `app/rag/` — RAG 核心管线：切分 → 向量化 → 两级检索（ChromaDB 粗检索 + 重排序） → 生成
- `app/document/` — 文档解析，`loader.py` 按文件类型分发到 7 种格式解析器
- `app/llm/` — 抽象基类 + DeepSeek 实现（chat、embed、rerank）
- `app/storage/` — ChromaDB 向量存储（每个知识库一个 collection）+ 本地文件存储
- `app/models/` — SQLAlchemy ORM 模型 + Pydantic 请求/响应 schema

**前端**（`frontend/`）：SPA 应用，5 个页面（登录、注册、知识库管理、对话、历史）。对话页通过 `fetch` + `ReadableStream` 实现 SSE 流式输出。生产模式下由 FastAPI 托管 `frontend/dist/` 静态文件，所有非 API 路由回退到 `index.html`。

## 关键设计决策

- **两级检索**: ChromaDB 粗检索 top_k=20 → LLM 重排序 → 最终 top_k=5
- **用户隔离**: 所有数据按 `user_id` 隔离，JWT 中间件强制鉴权
- **异步文档处理**: 上传接口立即返回，`BackgroundTasks` 后台解析/索引
- **ChromaDB collection**: 命名为 `kb_{kb_id}`，每个知识库独立一个 collection
