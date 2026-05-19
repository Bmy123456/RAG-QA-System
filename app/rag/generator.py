from typing import AsyncIterator
from app.llm.deepseek import DeepSeekLLM

SYSTEM_PROMPT = """你是一个基于文档知识库的智能助手。请严格根据提供的文档内容回答问题。

规则：
1. 仅使用提供的文档片段回答，不要编造信息
2. 如果文档中没有相关信息，请明确说明"根据已有文档无法回答此问题"
3. 回答时引用来源，使用 [1] [2] 等标记
4. 回答应简洁、准确、有条理"""


def build_prompt(question: str, chunks: list[dict], history: list[dict] | None = None) -> list[dict]:
    context_parts = []
    for i, chunk in enumerate(chunks, 1):
        source = chunk["metadata"].get("filename", "未知")
        page = chunk["metadata"].get("page", "")
        page_str = f" P{page}" if page else ""
        context_parts.append(f"[{i}] {source}{page_str}:\n{chunk['text']}")

    context_text = "\n\n".join(context_parts)

    user_message = f"""相关文档片段：

{context_text}

---

用户问题：{question}

请根据上述文档片段回答用户问题。"""

    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    if history:
        messages.extend(history)
    messages.append({"role": "user", "content": user_message})
    return messages


async def generate_answer(messages: list[dict]) -> AsyncIterator[str]:
    llm = DeepSeekLLM()
    async for chunk in llm.chat_stream(messages):
        yield chunk
