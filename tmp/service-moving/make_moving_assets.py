from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parent
FONT_REGULAR = "/Library/Fonts/Arial Unicode.ttf"
FONT_BOLD = "/System/Library/Fonts/SFNS.ttf"


def font(size, bold=False):
    path = FONT_BOLD if bold else FONT_REGULAR
    try:
        return ImageFont.truetype(path, size)
    except OSError:
        return ImageFont.truetype(FONT_REGULAR, size)


def cover(image, size):
    image = image.convert("RGB")
    target_w, target_h = size
    scale = max(target_w / image.width, target_h / image.height)
    resized = image.resize((round(image.width * scale), round(image.height * scale)), Image.LANCZOS)
    left = (resized.width - target_w) // 2
    top = (resized.height - target_h) // 2
    return resized.crop((left, top, left + target_w, top + target_h))


def rounded_rect(draw, box, radius, fill):
    draw.rounded_rectangle(box, radius=radius, fill=fill)


def make_og():
    img = cover(Image.open(ROOT / "source-og.png"), (1200, 630)).convert("RGBA")
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    for x in range(0, 780):
        alpha = int(188 * (1 - x / 780))
        od.line([(x, 0), (x, 630)], fill=(20, 31, 42, alpha))
    img = Image.alpha_composite(img, overlay)
    draw = ImageDraw.Draw(img)

    rounded_rect(draw, (62, 58, 330, 104), 18, (36, 108, 128, 232))
    draw.text((84, 68), "СТАМБУЛ И ТУРЦИЯ", font=font(22, True), fill=(255, 255, 255, 255))

    draw.text((62, 150), "Переезд", font=font(86, True), fill=(255, 255, 255, 255))
    draw.text((66, 250), "под ключ", font=font(66, True), fill=(255, 255, 255, 255))
    draw.text((66, 343), "Упаковка • разборка • сборка", font=font(30, False), fill=(238, 248, 250, 255))

    rounded_rect(draw, (62, 414, 572, 526), 24, (255, 255, 255, 232))
    draw.text((92, 438), "Погрузка и выгрузка", font=font(33, True), fill=(28, 66, 78, 255))
    draw.text((92, 480), "мебель, техника, коробки", font=font(24, False), fill=(42, 86, 99, 255))

    draw.text((64, 568), "Помощь с переездом дома, офиса и квартиры", font=font(23, False), fill=(255, 255, 255, 240))
    img.convert("RGB").save(ROOT / "pereezd-og.png", quality=95)


def make_reels_clean(source, output):
    cover(Image.open(ROOT / source), (1080, 1920)).save(ROOT / output, quality=95)


make_og()
make_reels_clean("source-reels-1.png", "pereezd-reels-1.png")
make_reels_clean("source-reels-2.png", "pereezd-reels-2.png")
