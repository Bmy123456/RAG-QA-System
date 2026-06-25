"""
文档摄取模块：将不同格式的原始文件转为标准化的 chunk 列表。

流程：文件 → 解析 → 清洗 → 分块 → 输出带元数据的 Chunk 列表
"""

from __future__ import annotations

import re
import unicodedata
import uuid
from dataclasses import dataclass, field

from backend.utils.file_parser import parse_file, PageContent
from backend.utils.text_splitter import (
    TextChunk,
    split_fixed,
    split_semantic,
    split_hierarchical,
    get_tokenizer,
    count_tokens,
)


# ---------------------------------------------------------------------------
# 输出数据类
# ---------------------------------------------------------------------------

@dataclass
class ChunkMetadata:
    """每个 chunk 的元数据"""
    filename: str
    file_type: str              # pdf / docx / xlsx / pptx / txt / md / html / image / eml
    chunk_index: int            # 在同级中的序号（从 0 开始）
    page: int | None            # 页码（PDF/PPT 有）
    section_title: str | None   # 章节标题
    start_char: int             # 在原文中的起始字符位置
    end_char: int               # 在原文中的结束字符位置
    token_count: int            # chunk 的 token 数
    parent_id: str | None       # 所属 parent chunk 的 chunk_id（仅 child 有值）
    chunk_level: str            # "parent" 或 "child"


@dataclass
class Chunk:
    """标准化的 chunk 输出"""
    chunk_id: str               # UUID
    text: str                   # 清洗后的文本
    metadata: ChunkMetadata


# ---------------------------------------------------------------------------
# 文本清洗
# ---------------------------------------------------------------------------

# 页码模式（中英文）
_PAGE_NUM_PATTERN = re.compile(
    r"^\s*(?:"
    r"(?:page|PAGE)\s*\d+"           # Page 1, PAGE 1
    r"|(?:第\s*\d+\s*页)"             # 第1页, 第 1 页
    r"|-\s*\d+\s*-"                   # - 1 -
    r"|\d+\s*/\s*\d+"                 # 1/10
    r"|(?:-\s*)\d+\s*(?:-\s*)?$"     # - 1 - 或 -1-
    r")\s*$",
    re.MULTILINE,
)

# 连续空行（3行以上 → 2行）
_MULTI_BLANK_LINES = re.compile(r"\n{3,}")

# 零宽字符
_ZERO_WIDTH = re.compile(r"[​‌‍﻿­]")

# 全角数字和字母 → 半角
_FW_DIGIT = str.maketrans(
    "０１２３４５６７８９",
    "0123456789",
)
_FW_ALPHA = str.maketrans(
    "ＡＢＣＤＥＦＧＨＩＪＫＬＭＮＯＰＱＲＳＴＵＶＷＸＹＺ"
    "ａｂｃｄｅｆｇｈｉｊｋｌｍｎｏｐｑｒｓｔｕｖｗｘｙｚ",
    "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    "abcdefghijklmnopqrstuvwxyz",
)


def _clean_segment(text: str) -> str:
    """对单个文本片段执行清洗（不含代码/表格保护逻辑）。"""
    text = _MULTI_BLANK_LINES.sub("\n\n", text)
    text = _PAGE_NUM_PATTERN.sub("", text)
    text = _ZERO_WIDTH.sub("", text)
    text = text.translate(_FW_DIGIT)
    text = text.translate(_FW_ALPHA)
    text = unicodedata.normalize("NFKC", text)
    text = _MULTI_BLANK_LINES.sub("\n\n", text)
    return text.strip()


def clean_text(text: str) -> str:
    """文本清洗（跳过代码块和表格保护区域）。

    1. 统一换行符（\\r\\n → \\n）
    2. 去除连续空行（3行以上 → 2行）
    3. 删除页码行
    4. 特殊字符标准化（全角→半角，零宽字符删除）
    5. 去除首尾空白

    代码块和表格区域保持原样不做清洗。
    """
    from backend.utils.text_splitter import _extract_special_regions

    # 1. 统一换行符
    text = text.replace("\r\n", "\n").replace("\r", "\n")

    # 2. 提取保护区域（代码/表格）
    regions = _extract_special_regions(text)

    if not regions:
        return _clean_segment(text)

    # 3. 分段清洗：普通区域正常清洗，保护区域原样保留
    result_parts: list[str] = []
    pos = 0
    for region in regions:
        if region.start > pos:
            segment = text[pos:region.start]
            cleaned = _clean_segment(segment)
            if cleaned:
                result_parts.append(cleaned)
        result_parts.append(text[region.start:region.end])
        pos = region.end

    # 最后一段
    if pos < len(text):
        cleaned = _clean_segment(text[pos:])
        if cleaned:
            result_parts.append(cleaned)

    return "\n\n".join(result_parts)


# ---------------------------------------------------------------------------
# 主入口
# ---------------------------------------------------------------------------

def ingest_file(
    file_path: str,
    chunk_strategy: str = "fixed",
    chunk_size: int = 512,
    chunk_overlap: int = 64,
    parent_chunk_size: int = 2048,
    tokenizer_model: str = "gpt-4o",
    on_progress=None,
) -> list[Chunk]:
    """文档摄取主入口。

    参数:
        file_path:          文件路径
        chunk_strategy:     分块策略 "fixed" | "semantic" | "hierarchical"
        chunk_size:         child chunk 的 token 数
        chunk_overlap:      重叠 token 数
        parent_chunk_size:  parent chunk 的 token 数（仅 hierarchical 模式）
        tokenizer_model:    tiktoken 使用的模型名
        on_progress:        进度回调 Callable[[int, str], None]，参数为 (progress_percent, message)

    返回:
        list[Chunk] — 标准化的 chunk 列表
    """
    # 0. 准备 tokenizer
    enc = get_tokenizer(tokenizer_model)

    # 1. 解析文件
    if on_progress:
        on_progress(5, "正在解析文档…")
    parse_result = parse_file(file_path)
    filename = file_path.rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
    if on_progress:
        on_progress(20, "文档解析完成，正在清洗…")

    # 2. 文本清洗
    raw_text = clean_text(parse_result.text)
    pages = parse_result.pages
    if pages:
        pages = [PageContent(page_number=p.page_number, text=clean_text(p.text)) for p in pages]

    if not raw_text:
        return []

    if on_progress:
        on_progress(30, "文本清洗完成，正在分块…")

    # 3. 分块
    if chunk_strategy == "hierarchical":
        parent_tc, child_tc = split_hierarchical(
            raw_text, parent_chunk_size, chunk_size, chunk_overlap, enc, pages,
        )
        chunks = _text_chunks_to_chunks(
            parent_tc, filename, parse_result.file_type, enc,
            level="parent", parent_id_map=None,
        )
        # 构建 child → parent 的映射
        parent_id_map = _build_parent_map(parent_tc, child_tc, chunks)
        child_chunks = _text_chunks_to_chunks(
            child_tc, filename, parse_result.file_type, enc,
            level="child", parent_id_map=parent_id_map,
        )
        chunks.extend(child_chunks)
    else:
        if chunk_strategy == "semantic":
            text_chunks = split_semantic(raw_text, chunk_size, chunk_overlap, enc, pages)
        else:
            text_chunks = split_fixed(raw_text, chunk_size, chunk_overlap, enc, pages)

        chunks = _text_chunks_to_chunks(
            text_chunks, filename, parse_result.file_type, enc,
            level="parent", parent_id_map=None,
        )

    if on_progress:
        on_progress(40, f"分块完成（{len(chunks)} 块），正在向量化…")

    return chunks


# ---------------------------------------------------------------------------
# 内部工具
# ---------------------------------------------------------------------------

def _text_chunks_to_chunks(
    text_chunks: list[TextChunk],
    filename: str,
    file_type: str,
    enc,
    level: str,
    parent_id_map: dict[int, str] | None,
) -> list[Chunk]:
    """将 TextChunk 列表转为标准 Chunk 列表"""
    result: list[Chunk] = []
    for i, tc in enumerate(text_chunks):
        chunk_id = str(uuid.uuid4())
        token_count = count_tokens(tc.text, enc)

        parent_id = None
        if level == "child" and parent_id_map is not None:
            parent_id = parent_id_map.get(i)

        meta = ChunkMetadata(
            filename=filename,
            file_type=file_type,
            chunk_index=i,
            page=tc.page,
            section_title=tc.section_title,
            start_char=tc.start_char,
            end_char=tc.end_char,
            token_count=token_count,
            parent_id=parent_id,
            chunk_level=level,
        )
        result.append(Chunk(chunk_id=chunk_id, text=tc.text, metadata=meta))

    return result


def _build_parent_map(
    parent_chunks: list[TextChunk],
    child_chunks: list[TextChunk],
    parent_std_chunks: list[Chunk],
) -> dict[int, str]:
    """为每个 child chunk 找到它所属的 parent chunk，返回 {child_index: parent_chunk_id}"""
    mapping: dict[int, str] = {}

    for ci, child in enumerate(child_chunks):
        child_mid = (child.start_char + child.end_char) / 2
        for pi, parent in enumerate(parent_chunks):
            if parent.start_char <= child_mid <= parent.end_char:
                mapping[ci] = parent_std_chunks[pi].chunk_id
                break
        else:
            # fallback: 用最后一个 parent
            if parent_std_chunks:
                mapping[ci] = parent_std_chunks[-1].chunk_id

    return mapping
