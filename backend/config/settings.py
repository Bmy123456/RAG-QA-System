"""
配置管理：从环境变量 / 配置文件加载设置。
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

# 加载 .env
load_dotenv()


# ---------------------------------------------------------------------------
# 基础配置
# ---------------------------------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
RAW_DIR = DATA_DIR / "raw"
PARSED_DIR = DATA_DIR / "parsed"
CHROMA_DIR = DATA_DIR / "chroma_db"
EVAL_DIR = DATA_DIR / "evaluation"

# 确保目录存在
for d in (RAW_DIR, PARSED_DIR, CHROMA_DIR, EVAL_DIR):
    d.mkdir(parents=True, exist_ok=True)

# 确保评估测试数据集存在（空文件）
for fname in ("retrieval_test.json", "generation_test.json"):
    fpath = EVAL_DIR / fname
    if not fpath.exists():
        fpath.write_text("[]", encoding="utf-8")


# ---------------------------------------------------------------------------
# 数据库
# ---------------------------------------------------------------------------

_default_db_url = f"sqlite:///{DATA_DIR / 'rag.db'}"
DATABASE_CONFIG = {
    "url": os.getenv("DATABASE_URL", "") or _default_db_url,
}


# ---------------------------------------------------------------------------
# Embedding 配置
# ---------------------------------------------------------------------------

EMBEDDING_CONFIG = {
    # 提供者: openai / deepseek / zhipu / qwen / mimo / sentence-transformers / bge-large
    "provider": os.getenv("EMBEDDING_PROVIDER", "mimo"),

    # 云端 API 配置
    "api_key": os.getenv("EMBEDDING_API_KEY", os.getenv("MIMO_API_KEY", os.getenv("DEEPSEEK_API_KEY", ""))),
    "base_url": os.getenv("EMBEDDING_BASE_URL", "") or "https://token-plan-cn.xiaomimimo.com/v1",
    "model": os.getenv("EMBEDDING_MODEL", "mimo-embed"),
    "dimensions": int(os.getenv("EMBEDDING_DIMENSIONS", "2048")),

    # 本地模型配置
    "device": os.getenv("EMBEDDING_DEVICE", "cpu"),
    "max_workers": int(os.getenv("EMBEDDING_MAX_WORKERS", "4")),

    # 通用配置
    "batch_size": int(os.getenv("EMBEDDING_BATCH_SIZE", "32")),
    "max_concurrency": int(os.getenv("EMBEDDING_MAX_CONCURRENCY", "10")),
    "normalize": True,
}


# ---------------------------------------------------------------------------
# 缓存配置
# ---------------------------------------------------------------------------

EMBEDDING_CACHE_CONFIG = {
    "enabled": os.getenv("CACHE_ENABLED", "true").lower() == "true",
    "backend": os.getenv("CACHE_BACKEND", "both"),  # memory / disk / both
    "db_path": str(DATA_DIR / "embedding_cache.db"),
}


# ---------------------------------------------------------------------------
# LLM 配置
# ---------------------------------------------------------------------------

LLM_CONFIG = {
    # 提供者: openai / deepseek / zhipu / qwen / mimo
    "provider": os.getenv("LLM_PROVIDER", "mimo"),
    "api_key": os.getenv("LLM_API_KEY", os.getenv("MIMO_API_KEY", os.getenv("DEEPSEEK_API_KEY", ""))),
    "base_url": os.getenv("LLM_BASE_URL", "") or "https://token-plan-cn.xiaomimimo.com/v1",
    "model": os.getenv("LLM_MODEL", "mimo-chat"),
    "temperature": float(os.getenv("LLM_TEMPERATURE", "0.3")),
    "max_tokens": int(os.getenv("LLM_MAX_TOKENS", "2048")),
}


# ---------------------------------------------------------------------------
# Reranker 配置
# ---------------------------------------------------------------------------

RERANKER_CONFIG = {
    # 提供者: bge-reranker / cohere / llm-pointwise / llm-pairwise
    # 或 LLM 别名: deepseek / openai / zhipu / qwen / mimo（自动映射到 llm-pointwise）
    "provider": os.getenv("RERANKER_PROVIDER", "mimo"),
    "top_k": int(os.getenv("RERANKER_TOP_K", "5")),

    # 跨编码器配置
    "model": os.getenv("RERANKER_MODEL", "BAAI/bge-reranker-v2-m3"),
    "device": os.getenv("RERANKER_DEVICE", "cpu"),

    # LLM 评分配置
    "api_key": os.getenv("RERANKER_API_KEY", os.getenv("MIMO_API_KEY", os.getenv("DEEPSEEK_API_KEY", ""))),
    "base_url": os.getenv("RERANKER_BASE_URL", "") or "https://token-plan-cn.xiaomimimo.com/v1",
    "llm_provider": os.getenv("RERANKER_LLM_PROVIDER", "mimo"),
    "max_concurrency": int(os.getenv("RERANKER_MAX_CONCURRENCY", "5")),
}


# ---------------------------------------------------------------------------
# 对话管理配置
# ---------------------------------------------------------------------------

CONVERSATION_CONFIG = {
    "max_turns": int(os.getenv("CONV_MAX_TURNS", "20")),
    "max_history_tokens": int(os.getenv("CONV_MAX_HISTORY_TOKENS", "2000")),
    "rewrite_enabled": os.getenv("CONV_REWRITE_ENABLED", "true").lower() == "true",
    "rewrite_detect": os.getenv("CONV_REWRITE_DETECT", "true").lower() == "true",
    "storage": os.getenv("CONV_STORAGE", "database"),  # memory / database
    "db_path": str(DATA_DIR / "conversations.db"),
    "llm_provider": os.getenv("LLM_PROVIDER", "mimo"),
    "llm_config": {
        "api_key": os.getenv("LLM_API_KEY", os.getenv("MIMO_API_KEY", os.getenv("DEEPSEEK_API_KEY", ""))),
        "base_url": os.getenv("LLM_BASE_URL", "") or "https://token-plan-cn.xiaomimimo.com/v1",
        "model": os.getenv("LLM_MODEL", "mimo-chat"),
    },
}


# ---------------------------------------------------------------------------
# 生成器配置
# ---------------------------------------------------------------------------

GENERATOR_CONFIG = {
    # 提供者: deepseek / openai / zhipu / qwen / mimo / ollama / vllm / tgi
    "provider": os.getenv("LLM_PROVIDER", "mimo"),
    "api_key": os.getenv("LLM_API_KEY", os.getenv("MIMO_API_KEY", os.getenv("DEEPSEEK_API_KEY", ""))),
    "base_url": os.getenv("LLM_BASE_URL", "") or "https://token-plan-cn.xiaomimimo.com/v1",
    "model": os.getenv("LLM_MODEL", "mimo-chat"),
    "temperature": float(os.getenv("LLM_TEMPERATURE", "0.3")),
    "max_tokens": int(os.getenv("LLM_MAX_TOKENS", "2048")),

    # 上下文窗口
    "max_context_tokens": None,  # None=自动计算
    "max_model_tokens": int(os.getenv("LLM_MAX_MODEL_TOKENS", "8192")),

    # 引用风格: inline / endnote / both
    "citation_style": "both",
}


# ---------------------------------------------------------------------------
# 向量数据库配置
# ---------------------------------------------------------------------------

VECTOR_STORE_CONFIG = {
    # 提供者: chroma / milvus / qdrant / weaviate
    "provider": os.getenv("VECTOR_STORE_PROVIDER", "chroma"),

    # ChromaDB 配置
    "persist_directory": str(CHROMA_DIR),
    "collection_mode": os.getenv("COLLECTION_MODE", "per-kb"),  # per-kb / single
    "collection_prefix": "kb_",
    "default_collection": "all_docs",

    # 远程模式（仅 Chroma client/server / 其他向量库）
    "host": os.getenv("VECTOR_STORE_HOST", None),
    "port": os.getenv("VECTOR_STORE_PORT", None),
}


# ---------------------------------------------------------------------------
# 检索配置
# ---------------------------------------------------------------------------

RETRIEVAL_CONFIG = {
    "initial_top_k": int(os.getenv("RETRIEVAL_INITIAL_TOP_K", "20")),
    "final_top_k": int(os.getenv("RETRIEVAL_FINAL_TOP_K", "5")),
}


# ---------------------------------------------------------------------------
# 认证配置
# ---------------------------------------------------------------------------

AUTH_CONFIG = {
    "secret_key": os.getenv("SECRET_KEY", "") or "change-me-in-production",
    "algorithm": "HS256",
    "access_token_expire_minutes": int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "30")),
    "refresh_token_expire_days": int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", "7")),
}


# ---------------------------------------------------------------------------
# 文档上传
# ---------------------------------------------------------------------------

MAX_UPLOAD_SIZE_MB = int(os.getenv("MAX_UPLOAD_SIZE_MB", "50"))


# ---------------------------------------------------------------------------
# 知识库权限
# ---------------------------------------------------------------------------

ALLOW_PUBLIC_KB = os.getenv("ALLOW_PUBLIC_KB", "true").lower() == "true"
KB_SHARING_ENABLED = os.getenv("KB_SHARING_ENABLED", "false").lower() == "true"


# ---------------------------------------------------------------------------
# 监控与评估
# ---------------------------------------------------------------------------

QA_LOGGING_ENABLED = os.getenv("QA_LOGGING_ENABLED", "true").lower() == "true"
