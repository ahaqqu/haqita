from pathlib import Path

from PIL import Image

WORK_DIR = Path("work")


def split_image_halves(img_path: str) -> tuple[str, str]:
    img = Image.open(img_path).convert('RGB')
    w, h = img.size
    stem = Path(img_path).stem

    WORK_DIR.mkdir(parents=True, exist_ok=True)

    top_path = WORK_DIR / f"{stem}_top.jpg"
    bot_path = WORK_DIR / f"{stem}_bot.jpg"

    img.crop((0, 0, w, h // 2)).save(str(top_path), 'JPEG', quality=92)
    img.crop((0, h // 2, w, h)).save(str(bot_path), 'JPEG', quality=92)
    return str(top_path), str(bot_path)
