from pathlib import Path

from PIL import Image, ImageEnhance

WORK_DIR = Path("work")


def preprocess_for_ocr(img_path: str, cfg: dict) -> str:
    img = Image.open(img_path).convert('RGB')

    min_w = cfg['ocr']['image_min_width_px']
    if img.width < min_w:
        scale = min_w / img.width
        new_size = (int(img.width * scale), int(img.height * scale))
        img = img.resize(new_size, Image.LANCZOS)

    img = ImageEnhance.Contrast(img).enhance(cfg['ocr']['image_contrast_enhance'])
    img = ImageEnhance.Sharpness(img).enhance(cfg['ocr']['image_sharpness_enhance'])

    stem = Path(img_path).stem
    out_path = WORK_DIR / f"{stem}_proc.jpg"
    WORK_DIR.mkdir(parents=True, exist_ok=True)
    img.save(str(out_path), 'JPEG', quality=92)
    return str(out_path)


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
