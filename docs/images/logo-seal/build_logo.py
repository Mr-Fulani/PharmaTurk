"""Собирает файлы логотипа (сургучная печать с пальмой) из исходника владельца.

Запуск из корня репозитория (нужны Pillow, numpy, scipy и программа cwebp):

    python3 docs/images/logo-seal/build_logo.py [папка для файлов соцсетей]

Исходник — logo-source.webp рядом со скриптом: печать на чёрном фоне, без прозрачности.
Что и куда пишется — README.md рядом.
"""
import base64
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter
from scipy import ndimage as ndi

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
PUBLIC = ROOT / "frontend" / "public"
ASSETS = ROOT / "frontend" / "src" / "assets" / "logo"


def cut_out(path):
    """Печать без чёрного фона: RGBA того же размера, что исходник."""
    rgb = np.asarray(Image.open(path).convert("RGB")).astype(np.float32)
    value = rgb.max(axis=2)  # яркость: у красного сургуча это красный канал

    # Силуэт. Светлее порога — печать; тёмные трещины внутри закрывает заливка, а трещины,
    # выходящие на край, — замыкание (иначе фон «затёк» бы в печать по трещине).
    shape = ndi.binary_fill_holes(value > 24)
    disk = np.hypot(*np.mgrid[-9:10, -9:10]) <= 9
    shape = ndi.binary_fill_holes(ndi.binary_closing(shape, structure=disk))

    # Глубина: расстояние до края силуэта, внутрь со знаком «плюс», наружу — «минус».
    depth = np.where(shape, ndi.distance_transform_edt(shape), -ndi.distance_transform_edt(~shape))

    # Цвет сургуча у края: сглаженный цвет точек не ближе 5 px к краю, взятый из ближайшей такой точки.
    deep = depth >= 5
    weight = np.maximum(ndi.gaussian_filter(deep.astype(np.float32), 2.5), 1e-6)
    smooth = np.stack([ndi.gaussian_filter(rgb[..., c] * deep, 2.5) / weight for c in range(3)], axis=2)
    _, (iy, ix) = ndi.distance_transform_edt(~deep, return_indices=True)
    wax = smooth[iy, ix]

    # Фон чёрный, поэтому цвет пикселя на краю = прозрачность × цвет сургуча.
    alpha = np.clip(value / np.maximum(wax.max(axis=2), 1.0), 0.0, 1.0)
    alpha = np.maximum(alpha, np.clip((depth - 1.0) / 3.0, 0.0, 1.0))  # глубже 4 px печать непрозрачна
    alpha[depth < -3] = 0.0
    alpha[deep] = 1.0

    # У полупрозрачных пикселей — чистый цвет сургуча без примеси чёрного (иначе на светлом фоне кайма).
    pure = np.clip(rgb / np.maximum(alpha, 1e-3)[..., None], 0, 255)
    mix = np.clip((alpha - 0.3) / 0.5, 0.0, 1.0)[..., None]
    color = np.where((alpha < 1.0)[..., None], wax * (1 - mix) + pure * mix, rgb)
    color[alpha == 0] = 0
    return Image.fromarray(np.dstack([color, alpha * 255.0]).round().astype(np.uint8), "RGBA")


def square(cut, pad=3):
    """Печать по центру прозрачного квадрата, обрезанного по её краям."""
    ys, xs = np.where(np.asarray(cut)[..., 3] > 5)
    crop = cut.crop((int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1))
    side = max(crop.size) + pad * 2
    canvas = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    canvas.alpha_composite(crop, ((side - crop.width) // 2, (side - crop.height) // 2))
    return canvas


def _linear(u8):
    c = u8.astype(np.float32) / 255.0
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def _srgb(linear):
    c = np.clip(linear, 0.0, 1.0)
    c = np.where(c <= 0.0031308, c * 12.92, 1.055 * c ** (1 / 2.4) - 0.055)
    return np.clip(c * 255.0 + 0.5, 0, 255).astype(np.uint8)


def scaled(master, size):
    """Уменьшение в линейном свете с учётом прозрачности: без тёмной каймы и потери яркости золота."""
    arr = np.asarray(master)
    alpha = arr[..., 3].astype(np.float32) / 255.0
    light = _linear(arr[..., :3]) * alpha[..., None]
    resize = lambda plane: np.asarray(Image.fromarray(plane, "F").resize((size, size), Image.LANCZOS))
    a = np.clip(resize(alpha), 0.0, 1.0)
    rgb = _srgb(np.stack([resize(light[..., c]) for c in range(3)], axis=2) / np.maximum(a, 1e-4)[..., None])
    rgb[a <= 0] = 0
    img = Image.fromarray(np.dstack([rgb, np.clip(a * 255.0 + 0.5, 0, 255).astype(np.uint8)]), "RGBA")
    # Мелким значкам — немного резкости, иначе пальма расплывается.
    amount = 60 if size <= 48 else 40 if size <= 128 else 25 if size <= 256 else 0
    if amount:
        *channels, a_band = img.split()
        sharp = Image.merge("RGB", channels).filter(ImageFilter.UnsharpMask(radius=0.6, percent=amount, threshold=0))
        img = Image.merge("RGBA", (*sharp.split(), a_band))
    return img


def on_background(master, side, color, fill):
    """Печать по центру непрозрачного квадрата; fill — какую долю стороны она занимает."""
    canvas = Image.new("RGBA", (side, side), color + (255,))
    inner = scaled(master, round(side * fill))
    canvas.alpha_composite(inner, ((side - inner.width) // 2,) * 2)
    return canvas.convert("RGB")


def save_png(img, path):
    """PNG с палитрой 256 цветов: в 4–5 раз легче полноцветного, на глаз то же самое."""
    img.quantize(256, method=Image.Quantize.FASTOCTREE, dither=Image.Dither.FLOYDSTEINBERG).save(path, optimize=True)


def webp_bytes(img, quality=90):
    with tempfile.TemporaryDirectory() as tmp:
        source, target = Path(tmp) / "in.png", Path(tmp) / "out.webp"
        img.save(source)
        # -sharp_yuv: без него граница красного и золотого размывается
        subprocess.run(
            ["cwebp", "-quiet", "-q", str(quality), "-m", "6", "-sharp_yuv", "-alpha_q", "100", str(source), "-o", str(target)],
            check=True,
        )
        return target.read_bytes()


def main():
    master = square(cut_out(HERE / "logo-source.webp"))
    ASSETS.mkdir(parents=True, exist_ok=True)

    # Шапка сайта: 38 px на экране, файлы под обычный, двойной и тройной экран.
    for size in (38, 76, 114):
        (ASSETS / f"seal-{size}.webp").write_bytes(webp_bytes(scaled(master, size)))

    # Значок вкладки: настоящий .ico с 16, 32 и 48 px и PNG для поисковиков и Android.
    frames = [scaled(master, size) for size in (48, 32, 16)]
    frames[0].save(PUBLIC / "favicon.ico", format="ICO", sizes=[(48, 48), (32, 32), (16, 16)], append_images=frames[1:])
    save_png(scaled(master, 120), PUBLIC / "favicon.png")
    save_png(scaled(master, 192), PUBLIC / "icon-192.png")

    # Значок на экране телефона: iOS заливает прозрачное чёрным, поэтому фон задан явно — чёрный, как у исходника.
    save_png(on_background(master, 180, (0, 0, 0), 0.86), PUBLIC / "apple-touch-icon.png")

    # Логотип для разметки организации (поисковики) и для картинок-превью.
    save_png(scaled(master, 512), PUBLIC / "logo-512.png")

    # Заглушка «нет фото»: печать вшита в SVG, внешние файлы картинка-SVG загрузить не может.
    placeholder = PUBLIC / "media-placeholder.svg"
    encoded = base64.b64encode(webp_bytes(scaled(master, 256), quality=85)).decode()
    svg, count = re.subn(r'href="data:image/webp;base64,[^"]*"', f'href="data:image/webp;base64,{encoded}"', placeholder.read_text())
    if count != 1:
        sys.exit("В media-placeholder.svg не найдено место для печати")
    placeholder.write_text(svg)

    # Файлы для внешних мест (соцсети, Telegram, Яндекс Бизнес): в репозиторий не идут.
    if len(sys.argv) > 1:
        kit = Path(sys.argv[1])
        kit.mkdir(parents=True, exist_ok=True)
        for size in (512, 1024):
            scaled(master, size).save(kit / f"mudaroba-logo-{size}-transparent.png", optimize=True)
        for name, color in (("black", (0, 0, 0)), ("cream", (253, 243, 231)), ("white", (255, 255, 255))):
            for size in (512, 1024):
                # 0.8: печать целиком остаётся в круге, которым соцсети обрезают аватарку
                on_background(master, size, color, 0.8).save(kit / f"mudaroba-avatar-{size}-{name}.png", optimize=True)


if __name__ == "__main__":
    main()
