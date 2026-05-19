from pathlib import Path
from app.document.parsers.pdf import parse_pdf
from app.document.parsers.word import parse_docx
from app.document.parsers.excel import parse_xlsx
from app.document.parsers.pptx_parser import parse_pptx
from app.document.parsers.image_ocr import parse_image
from app.document.parsers.web import parse_html
from app.document.parsers.email_msg import parse_eml
from app.document.cleaner import clean_text

PARSER_MAP = {
    "pdf": ("pdf", parse_pdf),
    "docx": ("docx", parse_docx),
    "doc": ("docx", parse_docx),
    "xlsx": ("xlsx", parse_xlsx),
    "xls": ("xlsx", parse_xlsx),
    "pptx": ("pptx", parse_pptx),
    "ppt": ("pptx", parse_pptx),
    "txt": ("txt", None),
    "md": ("md", None),
    "jpg": ("image", parse_image),
    "jpeg": ("image", parse_image),
    "png": ("image", parse_image),
    "html": ("web", None),
    "htm": ("web", None),
    "eml": ("email", parse_eml),
}


def get_file_type(extension: str) -> str | None:
    ext = extension.lower().lstrip(".")
    entry = PARSER_MAP.get(ext)
    return entry[0] if entry else None


def parse_document(file_path: str, file_type: str) -> list[dict]:
    ext = Path(file_path).suffix.lower().lstrip(".")
    entry = PARSER_MAP.get(ext)
    if entry is None:
        raise ValueError(f"Unsupported file type: {ext}")

    category, parser_fn = entry
    raw_text = ""

    if category == "pdf":
        pages = parser_fn(file_path)
        return [{"text": clean_text(p["text"]), "page": p["page"], "metadata": {"total_pages": p["total_pages"]}} for p in pages]

    elif category in ("docx", "xlsx", "pptx"):
        raw_text = parser_fn(file_path)

    elif category == "image":
        raw_text = parser_fn(file_path)

    elif category == "web":
        with open(file_path, "r", encoding="utf-8") as f:
            raw_text = parse_html(f.read())

    elif category == "email":
        raw_text = parser_fn(file_path)

    elif category in ("txt", "md"):
        with open(file_path, "r", encoding="utf-8") as f:
            raw_text = f.read()

    if raw_text:
        return [{"text": clean_text(raw_text), "page": None, "metadata": {}}]

    return []
