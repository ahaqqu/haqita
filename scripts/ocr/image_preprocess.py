from pathlib import Path

from PIL import Image, ImageEnhance

WORK_DIR = Path("work")


def preprocess_for_ocr(img_path: str, cfg: dict) -> str:
    provider = cfg['ocr']['provider']

    img = Image.open(img_path).convert('RGB')

    if provider == 'ollama':
        ollama_cfg = cfg['ocr'].get('ollama', {})
        min_w = ollama_cfg.get('image_min_width_px', 1400)
        if img.width < min_w:
            scale = min_w / img.width
            new_size = (int(img.width * scale), int(img.height * scale))
            img = img.resize(new_size, Image.LANCZOS)
        img = ImageEnhance.Contrast(img).enhance(ollama_cfg.get('image_contrast_enhance', 1.4))
        img = ImageEnhance.Sharpness(img).enhance(ollama_cfg.get('image_sharpness_enhance', 1.2))

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
