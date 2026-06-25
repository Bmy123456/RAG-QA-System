"""
对话管理模块：管理多轮对话状态与问题改写。

特性：
- 内存 / SQLite 数据库持久化，可配置
- 历史截断：固定轮数 + Token 数限制
- 问题改写：检测指代/省略，LLM 改写为完整独立问题
- 改写问题用于检索，原始问题保留用于生成
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import tiktoken

# ---------------------------------------------------------------------------
# 数据类
# ---------------------------------------------------------------------------

@dataclass
class Message:
    """单条对话消息"""
    role: str               # user / assistant
    content: str
    timestamp: str = ""     # ISO 格式
    metadata: dict = field(default_factory=dict)
    # metadata 可含: sources, rewritten_query, original_query 等


@dataclass
class ConversationSession:
    """对话会话"""
    session_id: str
    kb_id: int
    user_id: int = 0                   # 所属用户
    messages: list[Message] = field(default_factory=list)
    created_at: str = ""
    updated_at: str = ""


# ===========================================================================
# 存储接口
# ===========================================================================

class BaseConversationStore(ABC):
    """对话存储抽象基类。"""

    @abstractmethod
    async def create_session(self, kb_id: int, user_id: int = 0) -> ConversationSession:
        ...

    @abstractmethod
    async def get_session(self, session_id: str) -> ConversationSession | None:
        ...

    @abstractmethod
    async def add_message(self, session_id: str, message: Message) -> None:
        ...

    @abstractmethod
    async def get_history(self, session_id: str) -> list[Message]:
        ...

    @abstractmethod
    async def delete_session(self, session_id: str) -> bool:
        ...

    @abstractmethod
    async def list_sessions(self, kb_id: int | None = None, user_id: int | None = None) -> list[ConversationSession]:
        ...


# ---------------------------------------------------------------------------
# 内存存储
# ---------------------------------------------------------------------------

class MemoryStore(BaseConversationStore):
    """纯内存存储（进程内，重启丢失）。"""

    def __init__(self):
        self._sessions: dict[str, ConversationSession] = {}

    async def create_session(self, kb_id: int, user_id: int = 0) -> ConversationSession:
        now = datetime.utcnow().isoformat()
        session = ConversationSession(
            session_id=str(uuid.uuid4()),
            kb_id=kb_id,
            user_id=user_id,
            created_at=now,
            updated_at=now,
        )
        self._sessions[session.session_id] = session
        return session

    async def get_session(self, session_id: str) -> ConversationSession | None:
        return self._sessions.get(session_id)

    async def add_message(self, session_id: str, message: Message) -> None:
        session = self._sessions.get(session_id)
        if session:
            if not message.timestamp:
                message.timestamp = datetime.utcnow().isoformat()
            session.messages.append(message)
            session.updated_at = message.timestamp

    async def get_history(self, session_id: str) -> list[Message]:
        session = self._sessions.get(session_id)
        return list(session.messages) if session else []

    async def delete_session(self, session_id: str) -> bool:
        return self._sessions.pop(session_id, None) is not None

    async def list_sessions(self, kb_id: int | None = None, user_id: int | None = None) -> list[ConversationSession]:
        sessions = list(self._sessions.values())
        if kb_id is not None:
            sessions = [s for s in sessions if s.kb_id == kb_id]
        if user_id is not None:
            sessions = [s for s in sessions if s.user_id == user_id]
        sessions.sort(key=lambda s: s.updated_at, reverse=True)
        return sessions


# ---------------------------------------------------------------------------
# SQLite 持久化存储
# ---------------------------------------------------------------------------

class DatabaseStore(BaseConversationStore):
    """SQLite 持久化存储。"""

    def __init__(self, db_path: str = "data/conversations.db"):
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_tables()

    def _init_tables(self):
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS sessions (
                session_id TEXT PRIMARY KEY,
                kb_id INTEGER NOT NULL,
                user_id INTEGER DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                metadata TEXT DEFAULT '{}',
                FOREIGN KEY (session_id) REFERENCES sessions(session_id)
            );
            CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id);
        """)
        self._conn.commit()

    async def create_session(self, kb_id: int, user_id: int = 0) -> ConversationSession:
        now = datetime.utcnow().isoformat()
        session_id = str(uuid.uuid4())
        self._conn.execute(
            "INSERT INTO sessions (session_id, kb_id, user_id, created_at, updated_at) VALUES (?,?,?,?,?)",
            (session_id, kb_id, user_id, now, now),
        )
        self._conn.commit()
        return ConversationSession(session_id=session_id, kb_id=kb_id, user_id=user_id, created_at=now, updated_at=now)

    async def get_session(self, session_id: str) -> ConversationSession | None:
        row = self._conn.execute(
            "SELECT * FROM sessions WHERE session_id=?", (session_id,)
        ).fetchone()
        if not row:
            return None
        messages = await self.get_history(session_id)
        return ConversationSession(
            session_id=row["session_id"],
            kb_id=row["kb_id"],
            user_id=row["user_id"] if "user_id" in row.keys() else 0,
            messages=messages,
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    async def add_message(self, session_id: str, message: Message) -> None:
        if not message.timestamp:
            message.timestamp = datetime.utcnow().isoformat()
        self._conn.execute(
            "INSERT INTO messages (session_id, role, content, timestamp, metadata) VALUES (?,?,?,?,?)",
            (session_id, message.role, message.content, message.timestamp, json.dumps(message.metadata, ensure_ascii=False)),
        )
        self._conn.execute(
            "UPDATE sessions SET updated_at=? WHERE session_id=?",
            (message.timestamp, session_id),
        )
        self._conn.commit()

    async def get_history(self, session_id: str) -> list[Message]:
        rows = self._conn.execute(
            "SELECT * FROM messages WHERE session_id=? ORDER BY id ASC", (session_id,)
        ).fetchall()
        return [
            Message(
                role=row["role"],
                content=row["content"],
                timestamp=row["timestamp"],
                metadata=json.loads(row["metadata"]) if row["metadata"] else {},
            )
            for row in rows
        ]

    async def delete_session(self, session_id: str) -> bool:
        cursor = self._conn.execute("DELETE FROM sessions WHERE session_id=?", (session_id,))
        self._conn.execute("DELETE FROM messages WHERE session_id=?", (session_id,))
        self._conn.commit()
        return cursor.rowcount > 0

    async def list_sessions(self, kb_id: int | None = None, user_id: int | None = None) -> list[ConversationSession]:
        conditions = []
        params = []
        if kb_id is not None:
            conditions.append("kb_id=?")
            params.append(kb_id)
        if user_id is not None:
            conditions.append("user_id=?")
            params.append(user_id)

        if conditions:
            rows = self._conn.execute(
                f"SELECT * FROM sessions WHERE {' AND '.join(conditions)} ORDER BY updated_at DESC", params
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM sessions ORDER BY updated_at DESC"
            ).fetchall()

        sessions = []
        for row in rows:
            messages = await self.get_history(row["session_id"])
            sessions.append(ConversationSession(
                session_id=row["session_id"],
                kb_id=row["kb_id"],
                user_id=row["user_id"] if "user_id" in row.keys() else 0,
                messages=messages,
                created_at=row["created_at"],
                updated_at=row["updated_at"],
            ))
        return sessions


# ===========================================================================
# 问题改写
# ===========================================================================

_REWRITE_PROMPT = """根据对话历史，判断当前问题是否有指代词（如"它"、"这个"、"那个"、"其"）或省略了主语/宾语。
如果有，改写为完整的独立问题，使问题可以脱离对话历史独立理解。
如果没有，直接输出原始问题。

对话历史：
{history}

当前问题：{query}

只输出改写后的问题，不要输出任何解释。"""

_DETECT_PROMPT = """判断以下问题是否包含指代词（如"它"、"这个"、"那个"、"其"、"该"）或省略了主语/宾语，需要依赖对话历史才能理解。

对话历史：
{history}

问题：{query}

只输出 yes 或 no，不要输出其他内容。"""


class QueryRewriter:
    """问题改写器：检测指代/省略，LLM 改写为完整独立问题。"""

    def __init__(self, llm_client: Any, model: str = "deepseek-chat"):
        self._client = llm_client
        self._model = model

    @staticmethod
    def _format_history(history: list[Message], max_turns: int = 5) -> str:
        """格式化最近 N 轮历史"""
        recent = history[-max_turns * 2:]  # 每轮 user+assistant
        lines: list[str] = []
        for msg in recent:
            label = "用户" if msg.role == "user" else "助手"
            lines.append(f"{label}: {msg.content[:200]}")
        return "\n".join(lines) if lines else "（无历史对话）"

    async def detect_reference(self, query: str, history: list[Message]) -> bool:
        """检测问题是否包含指代/省略。"""
        if not history:
            return False

        history_text = self._format_history(history)
        prompt = _DETECT_PROMPT.format(history=history_text, query=query)

        try:
            resp = await self._client.chat.completions.create(
                model=self._model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0,
                max_tokens=5,
            )
            answer = resp.choices[0].message.content.strip().lower()
            return "yes" in answer
        except Exception:
            return False

    async def rewrite(self, query: str, history: list[Message]) -> str:
        """将问题改写为完整独立问题。"""
        history_text = self._format_history(history)
        prompt = _REWRITE_PROMPT.format(history=history_text, query=query)

        try:
            resp = await self._client.chat.completions.create(
                model=self._model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0,
                max_tokens=200,
            )
            rewritten = resp.choices[0].message.content.strip()
            return rewritten if rewritten else query
        except Exception:
            return query

    async def rewrite_if_needed(
        self,
        query: str,
        history: list[Message],
        force: bool = False,
        detect: bool = True,
    ) -> tuple[str, bool]:
        """统一入口。

        参数:
            query:   原始问题
            history: 对话历史
            force:   True 则跳过检测直接改写
            detect:  True 则先检测再改写，False 则每次改写

        返回:
            (改写后的问题, 是否被改写)
        """
        if not history:
            return query, False

        if force:
            rewritten = await self.rewrite(query, history)
            return rewritten, rewritten != query

        if detect:
            needs_rewrite = await self.detect_reference(query, history)
            if not needs_rewrite:
                return query, False

        rewritten = await self.rewrite(query, history)
        return rewritten, rewritten != query


# ===========================================================================
# 对话管理器（主入口）
# ===========================================================================

class ConversationManager:
    """对话管理器：编排存储 + 截断 + 问题改写。"""

    def __init__(self, config: dict | None = None):
        cfg = config or {}

        self._max_turns = cfg.get("max_turns", 20)
        self._max_history_tokens = cfg.get("max_history_tokens", 2000)
        self._rewrite_enabled = cfg.get("rewrite_enabled", True)
        self._rewrite_detect = cfg.get("rewrite_detect", True)

        # 存储
        storage = cfg.get("storage", "memory")
        if storage == "database":
            db_path = cfg.get("db_path", "data/conversations.db")
            self._store: BaseConversationStore = DatabaseStore(db_path)
        else:
            self._store = MemoryStore()

        # 问题改写器
        if self._rewrite_enabled:
            from openai import AsyncOpenAI
            llm_cfg = cfg.get("llm_config", {})
            provider = cfg.get("llm_provider", "deepseek")
            url_map = {
                "deepseek": "https://api.deepseek.com/v1",
                "openai": "https://api.openai.com/v1",
                "zhipu": "https://open.bigmodel.cn/api/paas/v4",
                "qwen": "https://dashscope.aliyuncs.com/compatible-mode/v1",
                "mimo": "https://api.xiaomi.com/v1",
            }
            base_url = llm_cfg.get("base_url") or url_map.get(provider, "https://api.deepseek.com/v1")
            api_key = llm_cfg.get("api_key", "")
            model = llm_cfg.get("model", "deepseek-chat")

            client = AsyncOpenAI(api_key=api_key, base_url=base_url)
            self._rewriter = QueryRewriter(client, model)
        else:
            self._rewriter = None

        self._tokenizer = tiktoken.get_encoding("cl100k_base")

    # -- 对话管理 -----------------------------------------------------------

    async def create_session(self, kb_id: int, user_id: int = 0) -> ConversationSession:
        """创建新会话"""
        return await self._store.create_session(kb_id, user_id)

    async def get_session(self, session_id: str) -> ConversationSession | None:
        """获取会话"""
        return await self._store.get_session(session_id)

    async def add_user_message(self, session_id: str, content: str, metadata: dict | None = None) -> Message:
        """添加用户消息"""
        msg = Message(role="user", content=content, metadata=metadata or {})
        await self._store.add_message(session_id, msg)
        return msg

    async def add_assistant_message(self, session_id: str, content: str, metadata: dict | None = None) -> Message:
        """添加助手消息"""
        msg = Message(role="assistant", content=content, metadata=metadata or {})
        await self._store.add_message(session_id, msg)
        return msg

    async def get_history(self, session_id: str) -> list[Message]:
        """获取完整历史"""
        return await self._store.get_history(session_id)

    async def get_truncated_history(self, session_id: str) -> list[Message]:
        """获取截断后的历史（用于送入 LLM）"""
        history = await self._store.get_history(session_id)
        return self.truncate_history(history)

    async def delete_session(self, session_id: str) -> bool:
        """删除会话"""
        return await self._store.delete_session(session_id)

    async def list_sessions(self, kb_id: int | None = None, user_id: int | None = None) -> list[ConversationSession]:
        """列出会话"""
        return await self._store.list_sessions(kb_id, user_id)

    # -- 问题改写 -----------------------------------------------------------

    async def process_query(
        self,
        query: str,
        session_id: str,
    ) -> tuple[str, str, bool]:
        """处理用户问题：改写 + 记录。

        参数:
            query:      用户原始问题
            session_id: 会话 ID

        返回:
            (检索用问题, 原始问题, 是否被改写)
        """
        history = await self._store.get_history(session_id)

        if self._rewrite_enabled and self._rewriter:
            rewritten, was_rewritten = await self._rewriter.rewrite_if_needed(
                query, history,
                detect=self._rewrite_detect,
            )
        else:
            rewritten, was_rewritten = query, False

        # 记录用户消息
        metadata = {}
        if was_rewritten:
            metadata["original_query"] = query
            metadata["rewritten_query"] = rewritten

        await self.add_user_message(session_id, query, metadata)

        return rewritten, query, was_rewritten

    # -- 历史截断 -----------------------------------------------------------

    def truncate_history(self, messages: list[Message]) -> list[Message]:
        """截断策略：同时满足 max_turns 和 max_history_tokens，取较小结果。"""
        if not messages:
            return []

        # 按轮数截断
        max_messages = self._max_turns * 2  # 每轮 user+assistant
        by_turns = messages[-max_messages:]

        # 按 token 数截断（从最新往前）
        by_tokens: list[Message] = []
        total_tokens = 0
        for msg in reversed(by_turns):
            msg_tokens = len(self._tokenizer.encode(msg.content))
            if total_tokens + msg_tokens > self._max_history_tokens:
                break
            by_tokens.insert(0, msg)
            total_tokens += msg_tokens

        # 取较小的结果
        if len(by_tokens) < len(by_turns):
            return by_tokens
        return by_turns

    # -- 属性 ---------------------------------------------------------------

    @property
    def rewrite_enabled(self) -> bool:
        return self._rewrite_enabled

    @property
    def max_turns(self) -> int:
        return self._max_turns
