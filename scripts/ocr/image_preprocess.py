from PIL import Image, ImageEnhance


def preprocess_for_ocr(img_path: str, cfg: dict) -> str:
    img = Image.open(img_path).convert('RGB')

    min_w = cfg['ocr']['image_min_width_px']
    if img.width < min_w:
        scale = min_w / img.width
        new_size = (int(img.width * scale), int(img.height * scale))
        img = img.resize(new_size, Image.LANCZOS)

    img = ImageEnhance.Contrast(img).enhance(cfg['ocr']['image_contrast_enhance'])
    img = ImageEnhance.Sharpness(img).enhance(cfg['ocr']['image_sharpness_enhance'])

    processed_path = str(img_path).replace('.jpg', '_proc.jpg').replace('.jpeg', '_proc.jpg')
    img.save(processed_path, 'JPEG', quality=92)
    return processed_path


def split_image_halves(img_path: str) -> tuple[str, str]:
    img = Image.open(img_path).convert('RGB')
    w, h = img.size
    top_path = img_path.replace('.jpg', '_top.jpg').replace('.jpeg', '_top.jpg')
    bot_path = img_path.replace('.jpg', '_bot.jpg').replace('.jpeg', '_bot.jpg')
    img.crop((0, 0, w, h // 2)).save(top_path, 'JPEG', quality=92)
    img.crop((0, h // 2, w, h)).save(bot_path, 'JPEG', quality=92)
    return top_path, bot_path
