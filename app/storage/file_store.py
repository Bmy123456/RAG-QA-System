import uuid
from pathlib import Path

FILES_DIR = Path("data/files")


def save_file(file_bytes: bytes, original_filename: str, user_id: int) -> tuple[str, str]:
    user_dir = FILES_DIR / str(user_id)
    user_dir.mkdir(parents=True, exist_ok=True)
    ext = Path(original_filename).suffix
    unique_name = f"{uuid.uuid4().hex}{ext}"
    dest = user_dir / unique_name
    dest.write_bytes(file_bytes)
    return str(dest), unique_name


def delete_file(file_path: str):
    p = Path(file_path)
    if p.exists():
        p.unlink()
