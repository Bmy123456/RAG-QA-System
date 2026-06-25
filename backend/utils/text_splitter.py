"""
分块策略层：提供 3 种分块模式。
- fixed:        固定长度（按 token 数切分，带重叠）
- semantic:     语义分块（按段落/标题等自然边界，再合并到目标大小）
- hierarchical: 层级分块（parent chunk → child chunk）

特殊内容处理：
- 代码块：按函数/类边界切割（Python 用 ast 解析，其他语言用正则）
- 表格：整体保留，转为 Markdown 格式存储
"""

from __future__ import annotations

import ast
import re
import uuid
from dataclasses import dataclass

import tiktoken

from backend.utils.file_parser import PageContent

# ---------------------------------------------------------------------------
# 数据类
# ---------------------------------------------------------------------------

@dataclass
class TextChunk:
    """分块输出（不含 chunk_id，由上层 ingestion.py 生成）"""
    text: str
    start_char: int
    end_char: int
    section_title: str | None
    page: int | None


# ---------------------------------------------------------------------------
# Tokenizer 工具
# ---------------------------------------------------------------------------

_DEFAULT_ENCODING = "cl100k_base"


def get_tokenizer(model: str = "gpt-4o"):
    """获取 tiktoken 编码器"""
    try:
        return tiktoken.encoding_for_model(model)
    except KeyError:
        return tiktoken.get_encoding(_DEFAULT_ENCODING)


def count_tokens(text: str, enc) -> int:
    """计算文本的 token 数"""
    return len(enc.encode(text))


# ---------------------------------------------------------------------------
# 特殊区域检测与处理（代码块、表格）
# ---------------------------------------------------------------------------

# 围栏代码块：```lang\n...\n```
_FENCED_CODE_RE = re.compile(r"```(\w*)\n(.*?)```", re.DOTALL)

# Markdown 表格：至少两行含 | 的文本，中间有 |---| 分隔行
_MD_TABLE_RE = re.compile(
    r"((?:\|[^\n]+\|\n){2,})",  # 至少 2 行以 | 开头和结尾的行
)

# 管道符表格行（DOCX/HTML 解析出的格式）
_PIPE_ROW_RE = re.compile(r"^.+\|.+\|?.+$", re.MULTILINE)


@dataclass
class SpecialRegion:
    """特殊区域标记"""
    start: int
    end: int
    region_type: str  # "code" | "table"
    content: str
    language: str = ""  # 代码语言


def _extract_special_regions(text: str) -> list[SpecialRegion]:
    """扫描全文，识别代码块和表格区域。"""
    regions: list[SpecialRegion] = []

    # 1. 围栏代码块
    for m in _FENCED_CODE_RE.finditer(text):
        lang = m.group(1) or "text"
        code = m.group(2)
        regions.append(SpecialRegion(
            start=m.start(), end=m.end(),
            region_type="code", content=code, language=lang,
        ))

    # 2. Markdown 表格（排除已被代码块覆盖的区域）
    code_ranges = {(r.start, r.end) for r in regions}
    for m in _MD_TABLE_RE.finditer(text):
        if any(m.start() >= s and m.end() <= e for s, e in code_ranges):
            continue
        # 验证是否真的是表格（含分隔行 |---|）
        lines = m.group(1).strip().split("\n")
        if len(lines) >= 2 and re.match(r"^\|[\s\-:|]+\|$", lines[1].strip()):
            regions.append(SpecialRegion(
                start=m.start(), end=m.end(),
                region_type="table", content=m.group(1).strip(),
            ))

    # 3. 管道符表格（连续 3 行以上含 | 的非代码行）
    if not any(r.region_type == "table" for r in regions):
        lines = text.split("\n")
        table_lines: list[tuple[int, str]] = []
        for i, line in enumerate(lines):
            stripped = line.strip()
            if _PIPE_ROW_RE.match(stripped) and stripped.count("|") >= 2:
                table_lines.append((i, stripped))
            else:
                if len(table_lines) >= 3:
                    _add_pipe_table_region(regions, text, lines, table_lines)
                table_lines = []
        if len(table_lines) >= 3:
            _add_pipe_table_region(regions, text, lines, table_lines)

    # 按位置排序，处理重叠（代码块优先于表格）
    regions.sort(key=lambda r: (r.start, -(r.end - r.start)))
    filtered: list[SpecialRegion] = []
    for r in regions:
        if not any(r.start >= f.start and r.end <= f.end for f in filtered):
            filtered.append(r)
    return filtered


def _add_pipe_table_region(
    regions: list[SpecialRegion],
    text: str,
    lines: list[str],
    table_lines: list[tuple[int, str]],
):
    """将管道符表格转为 Markdown 格式并添加为特殊区域。"""
    first_line_idx = table_lines[0][0]
    last_line_idx = table_lines[-1][0]
    # 计算字符位置
    start_char = sum(len(lines[i]) + 1 for i in range(first_line_idx))
    end_char = sum(len(lines[i]) + 1 for i in range(last_line_idx + 1))
    # 转 Markdown 表格
    md_rows = [row_text for _, row_text in table_lines]
    header = md_rows[0]
    # 自动生成分隔行（根据列数）
    col_count = header.count("|") + 1
    separator = "|" + "|".join(["---"] * col_count) + "|"
    md_table = header + "\n" + separator + "\n" + "\n".join(md_rows[1:])
    regions.append(SpecialRegion(
        start=start_char, end=end_char,
        region_type="table", content=md_table,
    ))


def _split_code_block(
    code: str,
    language: str,
    chunk_size: int,
    enc,
) -> list[str]:
    """按函数/类边界切割代码块。

    Python：用 ast 解析识别函数/类定义。
    其他语言：用正则匹配常见关键字边界。
    超长定义回退到按行切割。
    """
    language = language.lower()
    if language == "python":
        return _split_python_code(code, chunk_size, enc)
    else:
        return _split_generic_code(code, language, chunk_size, enc)


def _split_python_code(code: str, chunk_size: int, enc) -> list[str]:
    """用 ast 模块按函数/类定义切割 Python 代码。"""
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return _split_by_lines(code, chunk_size, enc)

    lines = code.split("\n")
    definitions: list[tuple[int, int, str]] = []  # (start_line, end_line, name)

    for node in ast.iter_child_nodes(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            start = node.lineno - 1  # ast 行号从 1 开始
            # 找到下一个顶级定义的起始行，或文件末尾
            end = getattr(node, "end_lineno", start + 1) - 1
            name = node.name
            definitions.append((start, end, name))

    if not definitions:
        return _split_by_lines(code, chunk_size, enc)

    # 按定义切割，每个定义前的代码归入上一个块
    chunks: list[str] = []
    prev_end = 0

    for start, end, name in definitions:
        # 定义前的"游离"代码
        preamble = "\n".join(lines[prev_end:start]).strip()
        if preamble:
            if count_tokens(preamble, enc) <= chunk_size:
                chunks.append(preamble)
            else:
                chunks.extend(_split_by_lines(preamble, chunk_size, enc))
        # 函数/类定义本身
        block = "\n".join(lines[start:end + 1]).strip()
        if block:
            if count_tokens(block, enc) <= chunk_size:
                chunks.append(block)
            else:
                chunks.extend(_split_by_lines(block, chunk_size, enc))
        prev_end = end + 1

    # 最后一个定义之后的代码
    tail = "\n".join(lines[prev_end:]).strip()
    if tail:
        if count_tokens(tail, enc) <= chunk_size:
            chunks.append(tail)
        else:
            chunks.extend(_split_by_lines(tail, chunk_size, enc))

    return [c for c in chunks if c.strip()]


def _split_generic_code(
    code: str,
    language: str,
    chunk_size: int,
    enc,
) -> list[str]:
    """用正则按函数/类关键字边界切割非 Python 代码。"""
    patterns = {
        "javascript": r"(?:^|\n)((?:export\s+)?(?:async\s+)?(?:function|class)\s+\w+)",
        "typescript": r"(?:^|\n)((?:export\s+)?(?:async\s+)?(?:function|class)\s+\w+)",
        "java": r"(?:^|\n)((?:public|private|protected|static|final|abstract)\s+)*\s*(?:class|interface|enum)\s+\w+",
        "go": r"(?:^|\n)func\s+",
        "rust": r"(?:^|\n)(?:pub\s+)?(?:fn|struct|impl|trait|enum)\s+",
        "c": r"(?:^|\n)(?:\w+\s+)+\w+\s*\([^)]*\)\s*\{",
        "cpp": r"(?:^|\n)(?:\w+\s+)+\w+\s*\([^)]*\)\s*(?:const\s*)?\{",
        "shell": r"(?:^|\n)(?:function\s+\w+|\w+\s*\(\)\s*\{)",
    }
    pattern = patterns.get(language)
    if not pattern:
        return _split_by_lines(code, chunk_size, enc)

    matches = list(re.finditer(pattern, code))
    if not matches:
        return _split_by_lines(code, chunk_size, enc)

    chunks: list[str] = []
    prev_end = 0
    for m in matches:
        preamble = code[prev_end:m.start()].strip()
        if preamble:
            if count_tokens(preamble, enc) <= chunk_size:
                chunks.append(preamble)
            else:
                chunks.extend(_split_by_lines(preamble, chunk_size, enc))
        prev_end = m.start()

    tail = code[prev_end:].strip()
    if tail:
        if count_tokens(tail, enc) <= chunk_size:
            chunks.append(tail)
        else:
            chunks.extend(_split_by_lines(tail, chunk_size, enc))

    return [c for c in chunks if c.strip()]


def _split_by_lines(text: str, chunk_size: int, enc) -> list[str]:
    """按行切割代码，保证不截断行。"""
    lines = text.split("\n")
    chunks: list[str] = []
    current: list[str] = []
    current_tokens = 0

    for line in lines:
        line_tokens = count_tokens(line, enc)
        if current_tokens + line_tokens > chunk_size and current:
            chunks.append("\n".join(current))
            current = []
            current_tokens = 0
        current.append(line)
        current_tokens += line_tokens

    if current:
        chunks.append("\n".join(current))

    return chunks


def _table_to_markdown(table_text: str) -> str:
    """将表格转为 Markdown 格式。已是 Markdown 的原样保留。"""
    lines = table_text.strip().split("\n")
    if not lines:
        return table_text

    # 检查是否已是 Markdown 表格（含 |---| 分隔行）
    for line in lines:
        if re.match(r"^\|[\s\-:|]+\|$", line.strip()):
            return table_text  # 已是 Markdown 格式

    # 管道符表格转 Markdown
    rows = [line.strip() for line in lines if line.strip()]
    if len(rows) < 2:
        return table_text

    header = rows[0]
    col_count = header.count("|") + 1
    separator = "|" + "|".join(["---"] * col_count) + "|"
    return header + "\n" + separator + "\n" + "\n".join(rows[1:])


# ---------------------------------------------------------------------------
# 特殊区域感知的统一分块入口
# ---------------------------------------------------------------------------

def _split_with_special_regions(
    text: str,
    chunk_size: int,
    chunk_overlap: int,
    enc,
    pages: list[PageContent] | None,
    normal_splitter,  # Callable[[str, int, int, ...], list[TextChunk]]
) -> list[TextChunk]:
    """先提取代码/表格保护区域，再对普通文本调用指定分块函数。"""
    regions = _extract_special_regions(text)
    if not regions:
        return normal_splitter(text, chunk_size, chunk_overlap, enc, pages)

    chunks: list[TextChunk] = []
    pos = 0

    for region in regions:
        # 区域前的普通文本
        if region.start > pos:
            normal_text = text[pos:region.start]
            if normal_text.strip():
                sub_chunks = normal_splitter(normal_text, chunk_size, chunk_overlap, enc, pages)
                for c in sub_chunks:
                    c.start_char += pos
                    c.end_char += pos
                chunks.extend(sub_chunks)

        # 特殊区域
        if region.region_type == "code":
            code_chunks = _split_code_block(region.content, region.language, chunk_size, enc)
            offset = text.find(region.content, pos)
            for i, code_text in enumerate(code_chunks):
                code_start = text.find(code_text, offset) if code_text in text[offset:] else offset
                if code_start == -1:
                    code_start = offset
                chunks.append(TextChunk(
                    text=code_text,
                    start_char=code_start,
                    end_char=code_start + len(code_text),
                    section_title=f"[代码块: {region.language}]",
                    page=_find_page_for_char(code_start, pages) if pages else None,
                ))
                offset = code_start + len(code_text)
        elif region.region_type == "table":
            md_table = _table_to_markdown(region.content)
            table_start = text.find(region.content[:20], pos)
            if table_start == -1:
                table_start = region.start
            chunks.append(TextChunk(
                text=md_table,
                start_char=table_start,
                end_char=table_start + len(md_table),
                section_title="[表格]",
                page=_find_page_for_char(table_start, pages) if pages else None,
            ))

        pos = region.end

    # 最后一段普通文本
    if pos < len(text):
        tail = text[pos:]
        if tail.strip():
            sub_chunks = normal_splitter(tail, chunk_size, chunk_overlap, enc, pages)
            for c in sub_chunks:
                c.start_char += pos
                c.end_char += pos
            chunks.extend(sub_chunks)

    return chunks


# ---------------------------------------------------------------------------
# 策略 1：固定长度分块
# ---------------------------------------------------------------------------

def _split_fixed_raw(
    text: str,
    chunk_size: int = 512,
    chunk_overlap: int = 64,
    enc=None,
    pages: list[PageContent] | None = None,
) -> list[TextChunk]:
    """固定长度分块原始逻辑（不含特殊区域处理）。"""
    if enc is None:
        enc = get_tokenizer()

    if not text.strip():
        return []

    # 按 token 编码
    tokens = enc.encode(text)
    total = len(tokens)

    if total <= chunk_size:
        return [TextChunk(
            text=text, start_char=0, end_char=len(text),
            section_title=None, page=_find_page_for_char(0, pages) if pages else None,
        )]

    chunks: list[TextChunk] = []
    start = 0
    while start < total:
        end = min(start + chunk_size, total)
        chunk_tokens = tokens[start:end]
        chunk_text = enc.decode(chunk_tokens)

        # 计算字符偏移（近似）
        char_start = len(enc.decode(tokens[:start]))
        char_end = len(enc.decode(tokens[:end]))

        # 清理边界：避免截断在单词中间
        chunk_text = _clean_chunk_boundary(chunk_text, is_start=(start == 0))

        chunks.append(TextChunk(
            text=chunk_text,
            start_char=char_start,
            end_char=char_end,
            section_title=None,
            page=_find_page_for_char(char_start, pages) if pages else None,
        ))

        start += chunk_size - chunk_overlap

    return chunks


def split_fixed(
    text: str,
    chunk_size: int = 512,
    chunk_overlap: int = 64,
    enc=None,
    pages: list[PageContent] | None = None,
) -> list[TextChunk]:
    """固定长度分块（含代码/表格保护区域处理）。"""
    if enc is None:
        enc = get_tokenizer()
    return _split_with_special_regions(text, chunk_size, chunk_overlap, enc, pages, _split_fixed_raw)


# ---------------------------------------------------------------------------
# 策略 2：语义分块
# ---------------------------------------------------------------------------

# 标题模式（中英文）
_HEADING_PATTERN = re.compile(
    r"^(?:#{1,6}\s+.+|[一二三四五六七八九十]+[、.]\s*.+|\d+(?:\.\d+)*[、.\s]\s*.+|[IVXLC]+[.、]\s*.+)",
    re.MULTILINE,
)


def _split_semantic_raw(
    text: str,
    chunk_size: int = 512,
    chunk_overlap: int = 64,
    enc=None,
    pages: list[PageContent] | None = None,
) -> list[TextChunk]:
    """语义分块原始逻辑（不含特殊区域处理）。"""
    if enc is None:
        enc = get_tokenizer()

    if not text.strip():
        return []

    # Step 1: 拆分为段落
    paragraphs = _split_into_paragraphs(text)

    # Step 2: 标记标题，构建 (text, section_title, start_char) 列表
    sections = _tag_sections(paragraphs, text)

    # Step 3: 合并到目标大小
    chunks: list[TextChunk] = []
    current_texts: list[str] = []
    current_title: str | None = None
    current_start = 0
    current_token_count = 0

    for sec_text, sec_title, sec_start in sections:
        sec_tokens = count_tokens(sec_text, enc)

        # 如果遇到新标题，先刷出当前积累
        if sec_title and current_texts and current_token_count > 0:
            merged = "\n\n".join(current_texts)
            chunks.append(TextChunk(
                text=merged, start_char=current_start,
                end_char=current_start + len(merged),
                section_title=current_title,
                page=_find_page_for_char(current_start, pages) if pages else None,
            ))
            current_texts = []
            current_token_count = 0

        if sec_title:
            current_title = sec_title

        # 如果单个段落超长，单独 fixed 切分
        if sec_tokens > chunk_size:
            if current_texts:
                merged = "\n\n".join(current_texts)
                chunks.append(TextChunk(
                    text=merged, start_char=current_start,
                    end_char=current_start + len(merged),
                    section_title=current_title,
                    page=_find_page_for_char(current_start, pages) if pages else None,
                ))
                current_texts = []
                current_token_count = 0

            sub_chunks = _split_fixed_raw(sec_text, chunk_size, chunk_overlap, enc)
            for sc in sub_chunks:
                sc.section_title = current_title
                sc.start_char = sec_start + sc.start_char
                sc.end_char = sec_start + sc.end_char
            chunks.extend(sub_chunks)
            current_start = sec_start + len(sec_text)
            continue

        # 合并判断
        if current_token_count + sec_tokens > chunk_size and current_texts:
            merged = "\n\n".join(current_texts)
            chunks.append(TextChunk(
                text=merged, start_char=current_start,
                end_char=current_start + len(merged),
                section_title=current_title,
                page=_find_page_for_char(current_start, pages) if pages else None,
            ))
            current_texts = []
            current_token_count = 0
            current_start = sec_start

        current_texts.append(sec_text)
        current_token_count += sec_tokens

    # 刷出剩余
    if current_texts:
        merged = "\n\n".join(current_texts)
        chunks.append(TextChunk(
            text=merged, start_char=current_start,
            end_char=current_start + len(merged),
            section_title=current_title,
            page=_find_page_for_char(current_start, pages) if pages else None,
        ))

    return chunks


def split_semantic(
    text: str,
    chunk_size: int = 512,
    chunk_overlap: int = 64,
    enc=None,
    pages: list[PageContent] | None = None,
) -> list[TextChunk]:
    """语义分块（含代码/表格保护区域处理）。"""
    if enc is None:
        enc = get_tokenizer()
    return _split_with_special_regions(text, chunk_size, chunk_overlap, enc, pages, _split_semantic_raw)


# ---------------------------------------------------------------------------
# 策略 3：层级分块
# ---------------------------------------------------------------------------

def split_hierarchical(
    text: str,
    parent_size: int = 2048,
    child_size: int = 512,
    overlap: int = 64,
    enc=None,
    pages: list[PageContent] | None = None,
) -> tuple[list[TextChunk], list[TextChunk]]:
    """层级分块：先生成 parent chunks，再在每个 parent 内部切 child chunks。

    返回:
        (parent_chunks, child_chunks)
        child chunk 通过 parent 的索引关联（上层 ingestion.py 负责赋 parent_id）
    """
    if enc is None:
        enc = get_tokenizer()

    if not text.strip():
        return [], []

    # Step 1: 用语义分块生成 parent chunks
    parent_chunks = split_semantic(text, parent_size, overlap, enc, pages)

    # Step 2: 在每个 parent 内部做 fixed 分块生成 child chunks
    all_children: list[TextChunk] = []

    for parent in parent_chunks:
        children = split_fixed(
            parent.text, child_size, overlap, enc,
            pages=pages,
        )
        # 调整子块的字符偏移（相对于全局文本）
        for child in children:
            child.start_char += parent.start_char
            child.end_char += parent.start_char
            child.section_title = parent.section_title
        all_children.extend(children)

    return parent_chunks, all_children


# ---------------------------------------------------------------------------
# 内部工具函数
# ---------------------------------------------------------------------------

def _split_into_paragraphs(text: str) -> list[str]:
    """按双换行拆分为段落，保留单换行的段落内容"""
    parts = re.split(r"\n{2,}", text)
    return [p.strip() for p in parts if p.strip()]


def _tag_sections(
    paragraphs: list[str], full_text: str,
) -> list[tuple[str, str | None, int]]:
    """标记每个段落的 section_title 和在原文中的起始位置。

    返回: [(paragraph_text, section_title_or_None, char_offset), ...]
    """
    result: list[tuple[str, str | None, int]] = []
    search_pos = 0
    current_title: str | None = None

    for para in paragraphs:
        idx = full_text.find(para, search_pos)
        if idx == -1:
            idx = search_pos

        if _HEADING_PATTERN.match(para):
            current_title = para.strip()

        result.append((para, current_title, idx))
        search_pos = idx + len(para)

    return result


def _find_page_for_char(char_pos: int, pages: list[PageContent]) -> int | None:
    """根据字符位置估算所在页码"""
    if not pages:
        return None

    offset = 0
    for page in pages:
        page_len = len(page.text) + 2  # +2 for "\n\n" join
        if char_pos < offset + page_len:
            return page.page_number
        offset += page_len

    return pages[-1].page_number if pages else None


def _clean_chunk_boundary(text: str, is_start: bool = False) -> str:
    """清理 chunk 边界，避免截断在句子/单词中间"""
    text = text.strip()
    if not text:
        return text

    # 如果不是第一个 chunk，跳过开头的不完整句子
    if not is_start:
        first_newline = text.find("\n")
        first_period = text.find("。")
        first_dot = text.find(". ")
        candidates = [i for i in [first_newline, first_period, first_dot] if i > 0]
        if candidates:
            cut = min(candidates)
            if cut < len(text) // 3:  # 只在前 1/3 范围内裁剪
                text = text[cut + 1:].strip()

    return text
