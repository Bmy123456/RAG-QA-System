"""
生成回答模块：基于上下文和用户问题调用大模型，产出最终答案。

特性：
- 流式输出 generate_stream()
- 引用标记（行内标注 + 文末引用）
- 动态上下文窗口管理（自动计算 token 限制）
- 可配置模型：OpenAI / DeepSeek / 智谱 / Qwen / MiMo / Ollama / vLLM / TGI
- 自定义 Prompt 模板
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, AsyncIterator

import tiktoken

# ---------------------------------------------------------------------------
# 数据类
# ---------------------------------------------------------------------------

@dataclass
class Source:
    """引用来源"""
    index: int              # 引用序号 [1] [2] ...
    chunk_id: str
    filename: str
    page: int | None
    snippet: str            # 原文片段


@dataclass
class GenerationResult:
    """生成结果"""
    answer: str             # 最终回答
    sources: list[Source]   # 引用来源列表
    model: str              # 使用的模型
    token_usage: dict       # token 用量 {"prompt": N, "completion": N, "total": N}


# ---------------------------------------------------------------------------
# Prompt 模板
# ---------------------------------------------------------------------------

DEFAULT_PROMPT = """你是一个专业助手。基于以下资料回答问题。
要求：
1. 严格基于提供的资料回答，不要编造信息
2. 如果资料不足，明确表示"根据已有资料无法回答该问题"
3. 回答时标注引用来源，格式为 [序号]
4. 回答结束后，另起一行写"来源："，列出所有引用的来源

---资料---
{context}
---资料结束---

{history_section}
用户问题：{question}"""

CONTEXT_ITEM_TEMPLATE = "[{index}] 来源: {filename}{page_info}\n{content}"

HISTORY_TEMPLATE = "历史对话：\n{history}\n"


# ---------------------------------------------------------------------------
# 上下文窗口管理
# ---------------------------------------------------------------------------

class ContextWindowManager:
    """管理送入 LLM 的上下文大小。"""

    def __init__(
        self,
        max_context_tokens: int | None = None,
        max_model_tokens: int = 8192,
        response_reserve: int = 2048,
        prompt_overhead: int = 500,
    ):
        self._max_context_tokens = max_context_tokens
        self._max_model_tokens = max_model_tokens
        self._response_reserve = response_reserve
        self._prompt_overhead = prompt_overhead

    def get_context_limit(self) -> int:
        """计算上下文 token 上限"""
        if self._max_context_tokens is not None:
            return self._max_context_tokens
        limit = self._max_model_tokens - self._response_reserve - self._prompt_overhead
        return max(512, limit)

    def build_context(
        self,
        documents: list,
        enc=None,
    ) -> tuple[str, list[Source]]:
        """将文档列表构建为上下文字符串，自动截断到 token 限制内。

        参数:
            documents: RerankResult 列表或类似对象（有 content/chunk_id/metadata/score）
            enc:       tiktoken 编码器

        返回:
            (context_text, sources_list)
        """
        if enc is None:
            enc = tiktoken.get_encoding("cl100k_base")

        limit = self.get_context_limit()
        context_parts: list[str] = []
        sources: list[Source] = []
        current_tokens = 0

        for i, doc in enumerate(documents):
            content = getattr(doc, "content", "") or getattr(doc, "text", "")
            metadata = getattr(doc, "metadata", {})
            chunk_id = getattr(doc, "chunk_id", "")

            filename = metadata.get("filename", "未知文件")
            page = metadata.get("page")
            page_info = f" 第{page}页" if page else ""

            # 构建引用项
            source = Source(
                index=i + 1,
                chunk_id=chunk_id,
                filename=filename,
                page=page,
                snippet=content[:200],
            )

            item_text = CONTEXT_ITEM_TEMPLATE.format(
                index=i + 1,
                filename=filename,
                page_info=page_info,
                content=content,
            )

            item_tokens = len(enc.encode(item_text))

            if current_tokens + item_tokens > limit:
                # 尝试截断当前文档
                remaining = limit - current_tokens
                if remaining > 100:
                    truncated_tokens = enc.encode(content)[:remaining]
                    truncated_text = enc.decode(truncated_tokens)
                    item_text = CONTEXT_ITEM_TEMPLATE.format(
                        index=i + 1,
                        filename=filename,
                        page_info=page_info,
                        content=truncated_text + "...(截断)",
                    )
                    context_parts.append(item_text)
                    sources.append(source)
                break

            context_parts.append(item_text)
            sources.append(source)
            current_tokens += item_tokens

        context = "\n\n".join(context_parts)
        return context, sources


# ---------------------------------------------------------------------------
# Prompt 构建
# ---------------------------------------------------------------------------

def build_messages(
    question: str,
    context: str,
    history: list[dict] | None = None,
    prompt_template: str = DEFAULT_PROMPT,
) -> list[dict]:
    """构建 OpenAI messages 格式。"""
    # 历史对话
    if history:
        history_lines: list[str] = []
        for msg in history:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            label = "用户" if role == "user" else "助手"
            history_lines.append(f"{label}: {content}")
        history_section = HISTORY_TEMPLATE.format(history="\n".join(history_lines))
    else:
        history_section = ""

    # 填充模板
    system_content = prompt_template.format(
        context=context,
        history_section=history_section,
        question=question,
    )

    messages = [
        {"role": "system", "content": system_content},
        {"role": "user", "content": question},
    ]

    return messages


# ---------------------------------------------------------------------------
# 引用解析
# ---------------------------------------------------------------------------

# 匹配 [1] [2] [12] 等引用标记
_CITE_PATTERN = re.compile(r"\[(\d+)\]")


def parse_cited_sources(answer: str, sources: list[Source]) -> list[Source]:
    """从回答文本中提取引用标记，返回被引用的 sources。"""
    cited_indices = set()
    for match in _CITE_PATTERN.finditer(answer):
        idx = int(match.group(1))
        cited_indices.add(idx)

    if not cited_indices:
        # 没有显式引用，返回全部
        return sources

    return [s for s in sources if s.index in cited_indices]


# ---------------------------------------------------------------------------
# 主类
# ---------------------------------------------------------------------------

# 模型提供商 → base_url 映射
_PROVIDER_URLS = {
    "deepseek": "https://api.deepseek.com/v1",
    "openai": "https://api.openai.com/v1",
    "zhipu": "https://open.bigmodel.cn/api/paas/v4",
    "qwen": "https://dashscope.aliyuncs.com/compatible-mode/v1",
    "mimo": "https://token-plan-cn.xiaomimimo.com/v1",
    "ollama": "http://localhost:11434/v1",
    "vllm": "http://localhost:8000/v1",
    "tgi": "http://localhost:8080/v1",
}


class AnswerGenerator:
    """生成回答主类。"""

    def __init__(self, config: dict | None = None):
        cfg = config or {}
        self._provider = cfg.get("provider", "deepseek")
        self._model = cfg.get("model", "deepseek-chat")
        self._temperature = cfg.get("temperature", 0.3)
        self._max_tokens = cfg.get("max_tokens", 2048)
        self._citation_style = cfg.get("citation_style", "both")  # inline / endnote / both
        self._prompt_template = cfg.get("prompt_template", DEFAULT_PROMPT)

        # LLM 客户端
        from openai import AsyncOpenAI
        base_url = cfg.get("base_url") or _PROVIDER_URLS.get(self._provider, "")
        api_key = cfg.get("api_key", "ollama")  # Ollama 不需要 key
        self._client = AsyncOpenAI(api_key=api_key, base_url=base_url)

        # 上下文窗口管理
        self._context_manager = ContextWindowManager(
            max_context_tokens=cfg.get("max_context_tokens"),
            max_model_tokens=cfg.get("max_model_tokens", 8192),
            response_reserve=cfg.get("response_reserve", self._max_tokens),
        )

    # -- 非流式生成 ---------------------------------------------------------

    async def generate(
        self,
        question: str,
        documents: list,
        history: list[dict] | None = None,
    ) -> GenerationResult:
        """非流式生成回答。

        参数:
            question:  用户问题
            documents: RerankResult 列表
            history:   历史对话 [{"role": "user/assistant", "content": "..."}]

        返回:
            GenerationResult
        """
        context, sources = self._context_manager.build_context(documents)
        messages = build_messages(question, context, history, self._prompt_template)

        resp = await self._client.chat.completions.create(
            model=self._model,
            messages=messages,
            temperature=self._temperature,
            max_tokens=self._max_tokens,
        )

        answer = resp.choices[0].message.content or ""
        cited_sources = parse_cited_sources(answer, sources)

        usage = {}
        if resp.usage:
            usage = {
                "prompt": resp.usage.prompt_tokens,
                "completion": resp.usage.completion_tokens,
                "total": resp.usage.total_tokens,
            }

        return GenerationResult(
            answer=answer,
            sources=cited_sources,
            model=self._model,
            token_usage=usage,
        )

    # -- 流式生成 -----------------------------------------------------------

    async def generate_stream(
        self,
        question: str,
        documents: list,
        history: list[dict] | None = None,
    ) -> AsyncIterator[str]:
        """流式生成回答，yield 文本片段。

        最后一个 yield 为特殊标记 "__SOURCES__" + sources JSON，
        供调用方解析引用来源。
        """
        context, sources = self._context_manager.build_context(documents)
        messages = build_messages(question, context, history, self._prompt_template)

        try:
            stream = await self._client.chat.completions.create(
                model=self._model,
                messages=messages,
                temperature=self._temperature,
                max_tokens=self._max_tokens,
                stream=True,
            )
        except Exception as e:
            raise RuntimeError(f"LLM API 调用失败: {type(e).__name__}: {str(e)}") from e

        full_answer = ""
        async for chunk in stream:
            try:
                delta = chunk.choices[0].delta
                if delta.content:
                    full_answer += delta.content
                    yield delta.content
            except (IndexError, AttributeError):
                continue

        # 流结束后，yield 引用来源
        cited_sources = parse_cited_sources(full_answer, sources)
        sources_data = [
            {
                "index": s.index,
                "chunk_id": s.chunk_id,
                "filename": s.filename,
                "page": s.page,
                "snippet": s.snippet,
            }
            for s in cited_sources
        ]
        import json
        yield f"__SOURCES__{json.dumps(sources_data, ensure_ascii=False)}"

    # -- 便捷方法 -----------------------------------------------------------

    @property
    def model_name(self) -> str:
        return self._model

    @property
    def context_limit(self) -> int:
        return self._context_manager.get_context_limit()
