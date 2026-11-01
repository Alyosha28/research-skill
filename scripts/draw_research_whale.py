#!/usr/bin/env python3
"""生成 README 使用的终端像素风研究鲸鱼动画。需要 Pillow。"""

import math
from pathlib import Path
import random

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "assets" / "research-whale-deepseek.gif"
FONT_PATH = "/System/Library/Fonts/Supplemental/Andale Mono.ttf"
WIDTH, HEIGHT = 320, 180
SCALE = 3
FRAME_COUNT = 24
DURATION_MS = 80

BG = "#06111d"
PANEL = "#0a1c2b"
GRID = "#102b3d"
CYAN = "#4de4e8"
BLUE = "#5b7fc0"
BLUE_DARK = "#38568c"
BLUE_LIGHT = "#d7f0ff"
WHITE = "#e8fbff"
MUTED = "#75a6b8"
GREEN = "#79f2b0"
YELLOW = "#ffd166"
CAP = "#172436"
INK = "#092137"


def font(size):
    return ImageFont.truetype(FONT_PATH, size)


def draw_background(draw, frame_index):
    draw.rectangle((0, 0, WIDTH, HEIGHT), fill=BG)
    for y in range(22, HEIGHT, 12):
        draw.line((0, y, WIDTH, y), fill=GRID, width=1)
    for x in range(0, WIDTH, 20):
        draw.line((x, 20, x, HEIGHT), fill=GRID, width=1)

    draw.rectangle((5, 5, 314, 174), fill=PANEL, outline=BLUE_DARK, width=1)
    draw.rectangle((5, 5, 314, 22), fill="#0d2638")
    draw.ellipse((12, 12, 15, 15), fill="#ff6b6b")
    draw.ellipse((19, 12, 22, 15), fill=YELLOW)
    draw.ellipse((26, 12, 29, 15), fill=GREEN)
    draw.text((37, 10), "DEEPSEEK // RESEARCH.EXE", font=font(7), fill=CYAN)
    draw.text((250, 10), f"F{frame_index + 1:02d}/24", font=font(7), fill=MUTED)

    random.seed(28)
    for _ in range(26):
        x = random.randint(15, 305)
        y = random.randint(30, 155)
        if (x // 8 + y // 8 + frame_index) % 5 == 0:
            draw.point((x, y), fill="#28526a")


def draw_spout(draw, frame_index):
    phase = frame_index % 8
    for index, (dx, dy) in enumerate(((-7, 0), (0, -5), (7, 0))):
        height = 11 + ((phase + index * 2) % 8) * 2
        x = 122 + dx
        y = 65 - height
        color = BLUE_LIGHT if index == 1 else CYAN
        draw.line((122, 66, x, y + 5), fill=color, width=2)
        draw.rectangle((x - 1, y, x + 1, y + 3), fill=color)


def draw_whale(draw, frame_index, bob):
    blink = frame_index in {10, 11, 22, 23}
    body_y = bob

    def points(values):
        return [(x, y + body_y) for x, y in values]

    def box(values):
        left, top, right, bottom = values
        return left, top + body_y, right, bottom + body_y

    # DeepSeek 图标轮廓：圆身、右上尾鳍、白色大腹部与弯月眼。
    draw.polygon(points(((158, 88), (174, 70), (183, 55), (187, 41), (191, 30),
                         (197, 26), (203, 29), (202, 40), (204, 48), (209, 53),
                         (216, 51), (224, 47), (232, 48), (234, 54), (231, 65),
                         (226, 75), (218, 83), (208, 88), (197, 89), (181, 94))), fill=BLUE)
    draw.polygon(points(((116, 38), (130, 25), (145, 28), (137, 39))), fill=BLUE)
    draw.ellipse(box((43, 32, 193, 154)), fill=BLUE, outline=BLUE_DARK, width=1)

    draw.polygon(points(((52, 76), (62, 70), (79, 69), (99, 74), (118, 83),
                         (135, 96), (150, 111), (164, 128), (174, 141), (161, 146),
                         (145, 146), (127, 142), (109, 134), (93, 123), (79, 110),
                         (67, 95), (58, 82))), fill=WHITE)
    draw.polygon(points(((128, 132), (137, 124), (145, 128), (141, 137), (134, 142))), fill=BLUE)

    if blink:
        draw.arc(box((157, 65, 181, 85)), 15, 165, fill=WHITE, width=3)
    else:
        draw.arc(box((153, 58, 184, 91)), 285, 105, fill=WHITE, width=4)
        draw.ellipse(box((155, 82, 160, 87)), fill=WHITE)
    draw.rectangle((177, 94 + body_y, 182, 97 + body_y), fill="#ff9eb5")

    draw.polygon(points(((174, 137), (190, 138), (204, 147), (195, 153),
                         (181, 151), (172, 145))), fill=BLUE_DARK)

    cap_y = body_y
    draw.polygon(((120, 43 + cap_y), (154, 27 + cap_y), (193, 38 + cap_y),
                  (159, 54 + cap_y)), fill=CAP, outline=CYAN)
    draw.rectangle((140, 40 + cap_y, 176, 58 + cap_y), fill=CAP, outline=BLUE_DARK)
    draw.line((154, 29 + cap_y, 154, 43 + cap_y), fill=YELLOW, width=1)
    sway = round(math.sin(frame_index * math.pi / 6) * 3)
    draw.line((187, 40 + cap_y, 191 + sway, 61 + cap_y), fill=YELLOW, width=1)
    draw.rectangle((189 + sway, 61 + cap_y, 193 + sway, 66 + cap_y), fill=YELLOW)

    draw.line((181, 139 + body_y, 207, 111), fill=BLUE_DARK, width=5)
    draw.line((182, 137 + body_y, 207, 109), fill=WHITE, width=2)


def draw_document(draw, frame_index, lens_x, lens_y):
    draw.polygon(((231, 61), (274, 61), (290, 77), (290, 139), (231, 139)), fill=WHITE)
    draw.polygon(((274, 61), (274, 77), (290, 77)), fill="#9ed8e6")
    draw.rectangle((231, 61, 290, 139), outline=BLUE_DARK, width=1)
    draw.text((239, 67), "RESULT", font=font(7), fill=BLUE_DARK)

    active_row = frame_index % 5
    for row in range(5):
        y = 82 + row * 10
        width = 34 if row % 2 == 0 else 26
        if row == active_row:
            draw.rectangle((237, y - 2, 278, y + 4), fill="#b8f3df")
        draw.line((239, y, 239 + width, y), fill=GREEN if row == active_row else MUTED, width=2)
    draw.text((240, 132), "NULL=KEEP", font=font(6), fill=BLUE_DARK)

    for offset in range(0, 16, 4):
        alpha = 90 - offset * 4
        draw.line((lens_x - 7 + offset, lens_y - 8, lens_x - 11 + offset, lens_y - 4),
                  fill=(255, 255, 255, max(25, alpha)), width=1)


def draw_magnifier(draw, lens_x, lens_y):
    draw.line((lens_x + 12, lens_y + 12, 207, 111), fill=INK, width=6)
    draw.line((lens_x + 12, lens_y + 12, 207, 111), fill=YELLOW, width=3)
    draw.ellipse((lens_x - 17, lens_y - 17, lens_x + 17, lens_y + 17),
                 fill=(77, 228, 232, 28), outline=INK, width=4)
    draw.ellipse((lens_x - 17, lens_y - 17, lens_x + 17, lens_y + 17), outline=CYAN, width=2)
    draw.line((lens_x - 8, lens_y - 8, lens_x - 2, lens_y - 12), fill=WHITE, width=2)
    draw.point((lens_x + 9, lens_y + 5), fill=WHITE)


def draw_footer(draw, frame_index):
    draw.text((15, 151), "OBSERVE > QUESTION > PROBE > COMPOSE", font=font(7), fill=GREEN)
    draw.text((15, 163), "evidence seam: common_support", font=font(7), fill=MUTED)
    if frame_index % 8 < 5:
        draw.rectangle((190, 163, 194, 169), fill=CYAN)
    draw.text((256, 157), "LOOP: ON", font=font(7), fill=CYAN)


def make_frame(frame_index):
    image = Image.new("RGBA", (WIDTH, HEIGHT), BG)
    draw = ImageDraw.Draw(image, "RGBA")
    draw_background(draw, frame_index)
    draw_spout(draw, frame_index)

    bob = round(math.sin(frame_index * math.pi / 12) * 2)
    lens_x = 249 + round(math.sin(frame_index * math.pi / 12) * 5)
    lens_y = 96 + round(math.cos(frame_index * math.pi / 12) * 4)
    draw_whale(draw, frame_index, bob)
    draw_document(draw, frame_index, lens_x, lens_y)
    draw_magnifier(draw, lens_x, lens_y)
    draw_footer(draw, frame_index)

    for y in range(24, HEIGHT, 3):
        draw.line((6, y, 313, y), fill=(0, 0, 0, 22), width=1)
    return image.convert("RGB").resize((WIDTH * SCALE, HEIGHT * SCALE), Image.Resampling.NEAREST)


def main():
    frames = [make_frame(index) for index in range(FRAME_COUNT)]
    palette = frames[0].convert("P", palette=Image.Palette.ADAPTIVE, colors=64)
    indexed = [frame.quantize(palette=palette, dither=Image.Dither.NONE) for frame in frames]
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    indexed[0].save(
        OUTPUT,
        save_all=True,
        append_images=indexed[1:],
        duration=DURATION_MS,
        loop=0,
        optimize=True,
        disposal=2,
    )
    print(f"已生成 {OUTPUT}：{FRAME_COUNT} 帧，{WIDTH * SCALE}×{HEIGHT * SCALE}。")


if __name__ == "__main__":
    main()
