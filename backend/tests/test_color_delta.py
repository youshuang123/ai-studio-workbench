"""颜色一致性（ΔE）纯函数测试。"""

import io

from PIL import Image

from app.services import color_delta


def _png(color, size=(80, 80)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, format="PNG")
    return buf.getvalue()


def _center_bg(fg, bg=(255, 255, 255), size=(100, 100)) -> bytes:
    img = Image.new("RGB", size, bg)
    for x in range(30, 70):
        for y in range(30, 70):
            img.putpixel((x, y), fg)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def test_same_image_delta_e_zero():
    raw = _center_bg((20, 50, 120))
    result = color_delta.compare_bytes(raw, raw)
    assert result["delta_e"] == 0
    assert result["level"] == "same"


def test_white_background_is_ignored():
    """白底 + 中间蓝色块，主色应该是蓝，不是白。"""
    img = Image.open(io.BytesIO(_center_bg((20, 50, 120))))
    color = color_delta.dominant_color(img)
    assert color is not None
    r, g, b = color
    assert b > r and b > g, f"主色应偏蓝，实际 {color}"


def test_similar_reds_are_close():
    """CIE76 对饱和色偏敏感，这里用肉眼几乎看不出差别的两档红。"""
    a = _center_bg((200, 30, 30))
    b = _center_bg((198, 32, 32))
    result = color_delta.compare_bytes(a, b)
    assert result["delta_e"] is not None
    assert result["delta_e"] < 3
    assert result["level"] == "same"


def test_red_vs_blue_is_different():
    a = _center_bg((200, 30, 30))
    b = _center_bg((30, 30, 200))
    result = color_delta.compare_bytes(a, b)
    assert result["delta_e"] > 10
    assert result["level"] == "different"


def test_pure_white_image_does_not_crash():
    raw = _png((255, 255, 255))
    result = color_delta.compare_bytes(raw, raw)
    # 全白时没有前景，仍然应该能算出 0
    assert result["delta_e"] == 0


def test_rgb_to_lab_known_values():
    # 纯白 L≈100，纯黑 L≈0
    assert abs(color_delta.rgb_to_lab((255, 255, 255))[0] - 100) < 0.5
    assert abs(color_delta.rgb_to_lab((0, 0, 0))[0]) < 0.5


def test_light_product_on_light_background():
    """浅色商品 + 浅灰背景：主色必须取商品，不能取背景。"""
    img = Image.new("RGB", (200, 200), (215, 215, 215))  # 浅灰背景
    for x in range(70, 130):
        for y in range(70, 130):
            img.putpixel((x, y), (250, 244, 232))  # 米白商品，在中心
    color = color_delta.dominant_color(img)
    assert color is not None
    assert color[0] > 240, f"应取商品色(米白)，实际 {color}"


def test_product_off_center_still_found():
    """商品偏左 + 灰背景：仍然要取到商品色。"""
    img = Image.new("RGB", (200, 200), (220, 220, 220))
    for x in range(10, 70):
        for y in range(60, 150):
            img.putpixel((x, y), (30, 80, 160))
    color = color_delta.dominant_color(img)
    assert color is not None
    assert color[2] > color[0], f"应取到蓝色，实际 {color}"


def test_two_light_products_are_close():
    """两张构图不同的米白商品图，ΔE 不应被背景差异放大。"""
    def make(bg, fg, box):
        img = Image.new("RGB", (200, 200), bg)
        for x in range(box[0], box[1]):
            for y in range(box[2], box[3]):
                img.putpixel((x, y), fg)
        return img

    a = make((215, 215, 215), (250, 244, 232), (70, 130, 70, 130))
    b = make((255, 255, 255), (250, 244, 232), (60, 140, 60, 140))
    result = color_delta.compare_images(a, b)
    assert result["delta_e"] is not None
    assert result["delta_e"] < 3, f"同为米白商品，ΔE 应很小，实际 {result}"


def test_center_fallback_when_product_not_centered():
    """商品不在中心（比如在左边）时，回退到全图去白，仍能取到商品色。"""
    img = Image.new("RGB", (200, 200), (255, 255, 255))
    for x in range(10, 60):
        for y in range(80, 140):
            img.putpixel((x, y), (30, 80, 160))  # 左侧蓝色块
    color = color_delta.dominant_color(img)
    assert color is not None
    assert color[2] > color[0], f"应取到蓝色，实际 {color}"


def test_compare_returns_colors():
    a = _center_bg((20, 50, 120))
    b = _center_bg((120, 50, 20))
    result = color_delta.compare_bytes(a, b)
    assert len(result["color_a"]) == 3
    assert len(result["color_b"]) == 3
