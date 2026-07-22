from pathlib import Path
import textwrap

from PIL import Image, ImageDraw, ImageFont, ImageFilter


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


def multiline(draw, xy, lines, fonts, fills, spacing=10):
    x, y = xy
    for text, fnt, fill in zip(lines, fonts, fills):
        draw.text((x, y), text, font=fnt, fill=fill)
        bbox = draw.textbbox((x, y), text, font=fnt)
        y = bbox[3] + spacing
    return y


def rounded_rect(draw, box, radius, fill):
    draw.rounded_rectangle(box, radius=radius, fill=fill)


def make_og():
    img = cover(Image.open(ROOT / "source-og.png"), (1200, 630)).convert("RGBA")
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    for x in range(0, 760):
        alpha = int(178 * (1 - x / 760))
        od.line([(x, 0), (x, 630)], fill=(16, 28, 27, alpha))
    img = Image.alpha_composite(img, overlay)
    draw = ImageDraw.Draw(img)

    rounded_rect(draw, (62, 58, 300, 104), 18, (42, 122, 102, 230))
    draw.text((84, 68), "ВЫЕЗД НА ДОМ", font=font(24, True), fill=(255, 255, 255, 255))

    title = ["Химчистка", "мягкой мебели"]
    multiline(
        draw,
        (62, 145),
        title,
        [font(70, True), font(70, True)],
        [(255, 255, 255, 255), (255, 255, 255, 255)],
        spacing=0,
    )
    draw.text((66, 335), "Диваны • кресла • стулья • матрасы", font=font(31, False), fill=(238, 250, 245, 255))

    rounded_rect(draw, (62, 410, 520, 515), 24, (255, 255, 255, 226))
    draw.text((92, 434), "Глубокая чистка", font=font(34, True), fill=(26, 67, 58, 255))
    draw.text((92, 476), "пятна, пыль и запахи", font=font(25, False), fill=(37, 91, 78, 255))

    draw.text((64, 560), "Стамбул и ближайшие районы", font=font(25, False), fill=(255, 255, 255, 240))
    img.convert("RGB").save(ROOT / "himchistka-myagkoj-mebeli-og.png", quality=95)


def make_reels(source, output, title, bullets, badge):
    img = cover(Image.open(ROOT / source), (1080, 1920)).convert("RGBA")
    blur = img.filter(ImageFilter.GaussianBlur(12))
    mask = Image.new("L", img.size, 0)
    md = ImageDraw.Draw(mask)
    md.rectangle((0, 0, 1080, 560), fill=190)
    md.rectangle((0, 1540, 1080, 1920), fill=145)
    img = Image.composite(blur, img, mask)

    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    od.rectangle((0, 0, 1080, 620), fill=(15, 33, 31, 130))
    od.rectangle((0, 1510, 1080, 1920), fill=(15, 33, 31, 142))
    img = Image.alpha_composite(img, overlay)
    draw = ImageDraw.Draw(img)

    rounded_rect(draw, (70, 84, 430, 146), 24, (42, 122, 102, 235))
    draw.text((98, 100), badge, font=font(28, True), fill=(255, 255, 255, 255))

    y = 210
    for line in textwrap.wrap(title, width=14):
        draw.text((70, y), line, font=font(82, True), fill=(255, 255, 255, 255))
        y += 92

    y = 1565
    for item in bullets:
        rounded_rect(draw, (70, y, 1010, y + 82), 28, (255, 255, 255, 226))
        draw.text((105, y + 22), item, font=font(33, False), fill=(27, 74, 64, 255))
        y += 102

    img.convert("RGB").save(ROOT / output, quality=95)


make_og()
make_reels(
    "source-reels-1.png",
    "himchistka-myagkoj-mebeli-reels-1.png",
    "Пятна и запахи уходят",
    ["Глубокая чистка ткани", "Без вывоза мебели", "Диваны, кресла, стулья"],
    "ХИМЧИСТКА",
)
make_reels(
    "source-reels-2.png",
    "himchistka-myagkoj-mebeli-reels-2.png",
    "Свежая мебель за один выезд",
    ["Работаем на дому", "Аккуратно и по ткани", "Стамбул и районы"],
    "НА ДОМУ",
)
