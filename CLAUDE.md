# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

多用户 RAG 智能问答系统。用户上传文档（PDF/Word/Excel/PPT/图片/网页/邮件），系统解析后建立向量索引，通过 LLM 回答问题并标注来源出处。

## 常用命令

```bash
# 后端
pip install -r requirements.txt
uvicorn backend.main:app --reload --port 8000

# 前端（React + Vite）
cd frontend
pnpm install
pnpm dev          # 开发模式，访问 http://localhost:5173（自动代理 /api 到后端）
pnpm build        # 构建生产版本到 frontend/dist/

# Docker
docker-compose up -d
```

启动前必须设置环境变量：`SECRET_KEY`、`MIMO_API_KEY`（或其他 LLM Provider 的 Key）。参考 `.env.example`。

## 架构

项目采用**模块化单体**架构，FastAPI 后端 + React 前端（Vite 构建）。生产模式下后端同时托管前端静态文件。

**请求链路**: React 前端 → API 路由 → 业务逻辑 → RAG 核心管线 → 响应

### API 层 — `backend/api/`

FastAPI 路由，均注册在 `/api/` 前缀下，仅处理 HTTP 请求/响应：

- `auth.py` — `/api/auth` — 注册、登录、刷新 Token、RBAC（user/admin 角色）
- `knowledge_base.py` — `/api/kb` — 知识库 CRUD、文档上传/状态/删除
- `chat.py` — `/api/chat` — SSE 流式对话，编排检索→重排序→生成
- `evaluation.py` — `/api/evaluation` — 反馈提交、查询日志、离线评估
- `admin.py` — `/api/admin/vectors` — 管理员向量库监控（统计、分页浏览、关键词搜索）

### RAG 核心 — `backend/core/`

- `ingestion.py` — 文档入库管线入口：解析→清洗→分块→向量化→存储
- `retrieval.py` — 混合检索：稠密（向量）+ 稀疏（BM25 + jieba 中文分词）+ RRF 融合，支持查询扩展（同义词 / HyDE）
- `reranker.py` — 重排序：bge-reranker / Cohere / LLM 逐点评分 / LLM 成对评分，工厂函数自动映射
- `embedding.py` — 多 Provider 嵌入（OpenAI/DeepSeek/智谱/通义/MiMo/SentenceTransformer/bge-large），双层缓存（内存 + SQLite）
- `generator.py` — LLM 生成回答，`ContextWindowManager` 自动截断上下文，解析 `[N]` 引用格式
- `vector_store.py` — ChromaDB 抽象层（每知识库一个 collection：`kb_{id}`），支持本地持久化和远程 HTTP
- `conversation.py` — 多轮对话状态管理（内存/SQLite）、LLM 问题改写（消除代词歧义）

### 数据层

- `backend/models/` — SQLAlchemy ORM 模型。**`Base` 定义在 `user.py`**，其他模型文件通过 `from backend.models.user import Base` 导入
- `backend/db/session.py` — SQLAlchemy 引擎 + `get_db` 依赖注入 + `init_db`（含自动迁移新列的 `_migrate_columns`）
- `backend/db/crud.py` — 全部数据库操作（知识库、文档、反馈、查询日志、统计导出）
- `backend/config/settings.py` — 全部配置通过环境变量加载，均有默认值

### 工具层

- `backend/utils/file_parser.py` — 注册式解析器分发，支持 7+ 格式（PDF/DOCX/XLSX/PPTX/TXT/MD/HTML/图片OCR/EML）
- `backend/utils/text_splitter.py` — 三种分块策略：固定（token + overlap）、语义（段落/标题边界）、层级（父块 2048 token → 子块 512 token）
- `backend/evaluation/` — 离线 RAG 质量评估（Precision@K、Recall@K、MRR、MAP、忠实度、BLEU）

### 前端 — `frontend/`

React 19 + TypeScript + Vite + Ant Design 5 单页应用。

- `src/api/` — API 层，axios 封装（JWT 拦截器）+ 各模块接口函数
- `src/stores/` — zustand 状态管理（authStore 用户认证、chatStore 对话状态）
- `src/pages/` — 页面组件：LoginPage（登录注册）、Chat（对话+会话切换）、KnowledgeBase（知识库+文档管理）、Feedback（反馈管理）、Evaluation（评估统计）、VectorMonitor（向量监控）
- `src/components/` — 通用组件：AppLayout（侧边栏布局）、SessionList（会话列表）、FeedbackButtons（反馈按钮组）
- SSE 流式对话通过 `fetch` + `ReadableStream` 实现，逐 token 实时渲染
- 开发模式下 Vite 自动代理 `/api` 到后端 `localhost:8000`

## 关键设计决策

- **两级检索**: ChromaDB 粗检索 top_k=20 → 重排序 → 最终 top_k=5
- **用户隔离**: 所有数据按 `user_id` 隔离，JWT 中间件强制鉴权，admin 角色可访问全部，公共知识库所有用户可读
- **异步文档处理**: 上传接口立即返回，`BackgroundTasks` 后台执行解析/分块/向量化，文档有 `progress` 字段跟踪进度
- **ChromaDB collection**: 命名为 `kb_{kb_id}`，每个知识库独立一个 collection，余弦相似度（HNSW）
- **ORM Base 单一定义**: 定义在 `backend/models/user.py`，其他模型文件统一从此导入。`backend/models/__init__.py` 统一导出所有模型，`backend/db/session.py` 导入它以确保 `create_all()` 前所有表已注册
- **无迁移工具**: 使用 SQLAlchemy `create_all()` 建表 + `_migrate_columns()` 自动 ALTER TABLE 添加新列。复杂 schema 变更需手动处理
- **多 SQLite 数据库**: 主数据 `rag.db`（SQLAlchemy）、对话历史 `conversations.db`（原生 sqlite3）、嵌入缓存 `embedding_cache.db`、BM25 索引作为 BLOB 存储在 `rag.db` 中
- **Embedding 缓存**: 双层缓存（进程内存 dict + SQLite），避免重复调用嵌入 API

## 已知限制

- Token 黑名单存储在进程内存 `set()` 中，重启后清空
- 无测试框架或测试套件
- Milvus/Qdrant/Weaviate 向量库接口仅为存根实现
