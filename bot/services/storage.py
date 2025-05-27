import os
from pathlib import Path

UPLOADS_DIR = Path("uploads")

def get_order_folder(telegram_id: int, order_id: str) -> Path:
    folder = UPLOADS_DIR / str(telegram_id) / order_id
    folder.mkdir(parents=True, exist_ok=True)
    return folder

def save_photo_to_order_folder(telegram_id: int, order_id: str, filename: str, file_bytes: bytes) -> str:
    folder = get_order_folder(telegram_id, order_id)
    filepath = folder / filename
    with open(filepath, "wb") as f:
        f.write(file_bytes)
    return str(filepath)
