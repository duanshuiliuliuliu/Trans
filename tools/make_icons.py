"""生成托盘图标（一次性脚本，仅在开发时运行，运行需 Pillow）。

用法：python tools/make_icons.py
"""
from __future__ import annotations

import os

from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASSETS = os.path.join(ROOT, "assets")
SIZES = (16, 20, 24, 32, 48, 64, 128, 256)

FONT_CANDIDATES = (
    r"C:\Windows\Fonts\msyhbd.ttc",
    r"C:\Windows\Fonts\msyh.ttc",
    r"C:\Windows\Fonts\simhei.ttf",
)


def load_font(size: int) -> ImageFont.FreeTypeFont:
    for path in FONT_CANDIDATES:
        if os.path.isfile(path):
            try:
                return ImageFont.truetype(path, size)
            except OSError:
                continue
    return ImageFont.load_default()


def rounded(size: int, background: tuple[int, int, int]) -> Image.Image:
    scale = 4
    canvas = Image.new("RGBA", (size * scale, size * scale), (0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas)
    radius = int(size * scale * 0.24)
    draw.rounded_rectangle(
        (0, 0, size * scale - 1, size * scale - 1), radius=radius, fill=background + (255,)
    )
    return canvas.resize((size, size), Image.LANCZOS)


def render(size: int, background: tuple[int, int, int], glyph: str, glyph_color: str) -> Image.Image:
    image = rounded(size, background)
    draw = ImageDraw.Draw(image)
    font = load_font(int(size * 0.78))
    box = draw.textbbox((0, 0), glyph, font=font)
    width = box[2] - box[0]
    height = box[3] - box[1]
    draw.text(
        ((size - width) / 2 - box[0], (size - height) / 2 - box[1]),
        glyph,
        font=font,
        fill=glyph_color,
    )
    return image


def build(name: str, background: tuple[int, int, int]) -> None:
    # 所有尺寸统一用字母 T：同一份 .ico 里混用两种字形时，Windows 会按显示场景
    # 挑不同尺寸（托盘 16px、资源管理器 32px 以上），看起来就像图标在变。
    frames = [render(size, background, "T", "#FFFFFF") for size in SIZES]
    target = os.path.join(ASSETS, name)
    # append_images 提供各尺寸的原图，bitmap_format 使用传统 DIB，兼容性最好
    frames[-1].save(
        target,
        format="ICO",
        sizes=[(size, size) for size in SIZES],
        append_images=frames[:-1],
        bitmap_format="bmp",
    )
    print(f"已生成 {target}")


def main() -> None:
    os.makedirs(ASSETS, exist_ok=True)
    build("icon.ico", (47, 111, 235))
    build("icon_off.ico", (140, 148, 158))


if __name__ == "__main__":
    main()
