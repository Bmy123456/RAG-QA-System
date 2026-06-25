"""
离线生成评估：忠实度 (Faithfulness)、相关性 (Relevance)、BLEU。

输入数据格式：
[
    {
        "question": "什么是RAG？",
        "context": "RAG是检索增强生成...",
        "answer": "RAG是一种...",
        "reference": "参考答案..."
    }
]
"""

from __future__ import annotations

import re
from collections import Counter


def evaluate_generation(test_data: list[dict]) -> dict:
    """执行生成评估。

    返回:
        {"faithfulness": 0.9, "relevance": 0.85, "bleu": 0.3, "num_samples": 10}
    """
    results = {
        "num_samples": len(test_data),
        "samples": [],
    }

    total_faithfulness = 0.0
    total_relevance = 0.0
    total_bleu = 0.0

    for item in test_data:
        question = item.get("question", "")
        context = item.get("context", "")
        answer = item.get("answer", "")
        reference = item.get("reference", "")

        faith = faithfulness(answer, context)
        rel = relevance(answer, question)
        bleu_score = bleu(answer, reference) if reference else 0.0

        total_faithfulness += faith
        total_relevance += rel
        total_bleu += bleu_score

        results["samples"].append({
            "question": question,
            "faithfulness": round(faith, 4),
            "relevance": round(rel, 4),
            "bleu": round(bleu_score, 4),
        })

    n = max(1, len(test_data))
    results["faithfulness"] = round(total_faithfulness / n, 4)
    results["relevance"] = round(total_relevance / n, 4)
    results["bleu"] = round(total_bleu / n, 4)

    return results


def faithfulness(answer: str, context: str) -> float:
    """忠实度：回答中有多少信息可以被上下文支持。

    使用简单的句子级匹配：
    1. 将回答拆分为句子
    2. 对每个句子，检查是否与上下文有重叠
    3. 返回被支持的句子比例
    """
    if not answer or not context:
        return 0.0

    answer_sents = _split_sentences(answer)
    context_sents = _split_sentences(context)

    if not answer_sents:
        return 0.0

    supported = 0
    for ans_sent in answer_sents:
        ans_tokens = _tokenize(ans_sent)
        if not ans_tokens:
            supported += 1
            continue

        for ctx_sent in context_sents:
            ctx_tokens = _tokenize(ctx_sent)
            overlap = len(ans_tokens & ctx_tokens)
            if overlap / len(ans_tokens) >= 0.5:
                supported += 1
                break

    return supported / len(answer_sents)


def relevance(answer: str, question: str) -> float:
    """相关性：回答与问题的相关程度。

    使用关键词重叠度量。
    """
    if not answer or not question:
        return 0.0

    q_tokens = _tokenize(question)
    a_tokens = _tokenize(answer)

    if not q_tokens:
        return 0.0

    overlap = len(q_tokens & a_tokens)
    return min(1.0, overlap / len(q_tokens) * 2)


def bleu(prediction: str, reference: str, max_n: int = 4) -> float:
    """简化的 BLEU 分数计算。"""
    if not prediction or not reference:
        return 0.0

    pred_tokens = prediction.split()
    ref_tokens = reference.split()

    if not pred_tokens or not ref_tokens:
        return 0.0

    # Brevity penalty
    bp = min(1.0, len(pred_tokens) / len(ref_tokens)) if len(pred_tokens) < len(ref_tokens) else 1.0

    scores = []
    for n in range(1, max_n + 1):
        pred_ngrams = _get_ngrams(pred_tokens, n)
        ref_ngrams = _get_ngrams(ref_tokens, n)

        if not pred_ngrams:
            scores.append(0.0)
            continue

        clipped = 0
        for ngram, count in pred_ngrams.items():
            clipped += min(count, ref_ngrams.get(ngram, 0))

        total = sum(pred_ngrams.values())
        scores.append(clipped / total if total > 0 else 0.0)

    # 几何平均
    if any(s == 0 for s in scores):
        return 0.0

    import math
    log_avg = sum(math.log(s) for s in scores) / len(scores)
    return bp * math.exp(log_avg)


# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------

def _split_sentences(text: str) -> list[str]:
    """中英文分句。"""
    sents = re.split(r'[。！？.!?\n]+', text)
    return [s.strip() for s in sents if s.strip()]


def _tokenize(text: str) -> set[str]:
    """简单分词（按字符或空格）。"""
    # 中文按字，英文按词
    tokens = set()
    for char in text:
        if '一' <= char <= '鿿':
            tokens.add(char)
    words = re.findall(r'[a-zA-Z]+', text.lower())
    tokens.update(words)
    return tokens


def _get_ngrams(tokens: list[str], n: int) -> Counter:
    """获取 n-gram 计数。"""
    ngrams = Counter()
    for i in range(len(tokens) - n + 1):
        ngram = tuple(tokens[i:i + n])
        ngrams[ngram] += 1
    return ngrams
