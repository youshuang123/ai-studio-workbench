"""颜色一致性：主色提取 + ΔE 色差（纯函数，免费，可单测）。

思路：
- 电商主图的背景是纯白/浅灰，真正能代表商品的像素在中间；
- 先剔除"接近纯白"的像素，再取剩余像素的中位色作为主色；
- 用 CIE76（Lab 欧氏距离）算 ΔE：够判断"颜色是否一致"，且不需要引入
  scikit-image / colour-science 这类重依赖。
"""

import io
from collections import Counter

from PIL import Image

# 判定为背景的阈值：RGB 三个通道都 ≥ 该值
WHITE_CUTOFF = 240

# 计算时的采样上限，避免大图拖慢
MAX_SAMPLES = 100_000


def _iter_pixels(img: Image.Image):
    img = img.convert("RGB")
    w, h = img.size
    total = w * h
    step = max(1, int((total / MAX_SAMPLES) ** 0.5))
    if step == 1:
        return list(img.getdata())
    pixels = []
    data = img.load()
    for y in range(0, h, step):
        for x in range(0, w, step):
            pixels.append(data[x, y])
    return pixels


def _mode_color(pixels: list[tuple[int, int, int]]) -> tuple[int, int, int] | None:
    """量化到 16 级投票，取最多的桶再求均值（抗噪）。"""
    if not pixels:
        return None

    def bucket(p):
        return (p[0] // 16, p[1] // 16, p[2] // 16)

    counter = Counter(bucket(p) for p in pixels)
    best = counter.most_common(1)[0][0]
    group = [p for p in pixels if bucket(p) == best]
    n = len(group)
    return (
        sum(p[0] for p in group) // n,
        sum(p[1] for p in group) // n,
        sum(p[2] for p in group) // n,
    )


def _corner_backgrounds(img: Image.Image) -> list[tuple[int, int, int]]:
    """四角颜色 = 背景色（商品不会同时占满四个角）。"""
    w, h = img.size
    pad = 4
    return [
        img.getpixel((pad, pad)),
        img.getpixel((w - 1 - pad, pad)),
        img.getpixel((pad, h - 1 - pad)),
        img.getpixel((w - 1 - pad, h - 1 - pad)),
    ]


def _dist2(a, b) -> int:
    return sum((x - y) ** 2 for x, y in zip(a, b))


# 与背景色的距离阈值（欧氏距离平方，25² = 625）
BG_TOLERANCE_SQ = 625


def dominant_color(img: Image.Image) -> tuple[int, int, int] | None:
    """返回商品主色 (r,g,b)。

    走过的两次坑（都留下了测试）：
    1. 只剔除"接近纯白"的像素 → 浅灰背景没被剔除，米白商品被判成灰背景（ΔE 假 12）；
    2. 只看中心区域 → 精修后构图略变，中心落在了背景上。

    现在的做法：**用四角颜色当背景基准**，偏离背景超过阈值的像素才算商品，
    再在这些像素里取众数。商品不会同时占满四个角，这个假设比"商品居中"更稳。
    """
    img = img.convert("RGB")
    backgrounds = _corner_backgrounds(img)
    pixels = _iter_pixels(img)

    foreground = [
        p
        for p in pixels
        if min(_dist2(p, bg) for bg in backgrounds) > BG_TOLERANCE_SQ
    ]

    # 前景太少（纯白图 / 商品贴满画面）→ 回退到全图众数
    if len(foreground) < max(50, len(pixels) * 0.02):
        return _mode_color(pixels)

    return _mode_color(foreground)


def rgb_to_lab(rgb: tuple[int, int, int]) -> tuple[float, float, float]:
    """sRGB → CIE Lab（D65）。"""

    def linearize(c: float) -> float:
        c = c / 255.0
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = (linearize(v) for v in rgb)
    x = r * 0.4124564 + g * 0.3575761 + b * 0.1804375
    y = r * 0.2126729 + g * 0.7151522 + b * 0.0721750
    z = r * 0.0193339 + g * 0.1191920 + b * 0.9503041

    xn, yn, zn = 0.95047, 1.0, 1.08883

    def f(t: float) -> float:
        return t ** (1 / 3) if t > 216 / 24389 else (24389 / 27 * t + 16) / 116

    fx, fy, fz = f(x / xn), f(y / yn), f(z / zn)
    return (116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz))


def delta_e_cie76(lab1: tuple[float, float, float], lab2: tuple[float, float, float]) -> float:
    return sum((a - b) ** 2 for a, b in zip(lab1, lab2)) ** 0.5


def compare_images(img_a: Image.Image, img_b: Image.Image) -> dict:
    """比较两张图的主色。

    返回 {"delta_e": float|None, "level": "same|slight|different|unknown",
          "color_a": [r,g,b]|None, "color_b": [r,g,b]|None}
    """
    ca = dominant_color(img_a)
    cb = dominant_color(img_b)
    if ca is None or cb is None:
        return {"delta_e": None, "level": "unknown", "color_a": ca, "color_b": cb}

    de = delta_e_cie76(rgb_to_lab(ca), rgb_to_lab(cb))
    if de <= 3:
        level = "same"
    elif de <= 6:
        level = "slight"
    else:
        level = "different"
    return {
        "delta_e": round(de, 2),
        "level": level,
        "color_a": list(ca),
        "color_b": list(cb),
    }


def compare_bytes(img_a: bytes, img_b: bytes) -> dict:
    return compare_images(Image.open(io.BytesIO(img_a)), Image.open(io.BytesIO(img_b)))
