"""主图 prompt 模板（纯函数，便于单测）。

注意：FLUX.1-schnell 是纯文生图，**看不到用户上传的商品图**。
2-1 只验证链路与成本，不承诺与原商品一致；一致性在 2-2 接入图生图模型后验收。
"""

NEGATIVE_PROMPT = (
    "text, watermark, logo, human, hand, blurry, distorted, extra objects, "
    "low quality, oversaturated, deformed"
)

_MAX_SELLING_POINTS = 200


def build_prompt(
    product_name: str,
    category: str = "",
    selling_points: str = "",
    color: str = "",
) -> str:
    name = (product_name or "").strip()
    if not name:
        raise ValueError("商品名称不能为空")

    lines = [
        "你是电商主图设计师。基于以下信息生成一张商品主图。",
        "",
        f"商品：{name}",
    ]
    if category and category.strip():
        lines.append(f"类目：{category.strip()}")
    if selling_points and selling_points.strip():
        points = selling_points.strip()[:_MAX_SELLING_POINTS]
        lines.append(f"卖点：{points}")
    if color and color.strip():
        lines.append(f"主色：{color.strip()}")

    lines += [
        "",
        "要求：",
        "1. 商品完整居中，占据画面 65%-75%，不裁切",
        "2. 纯白或浅灰渐变背景，无杂物、无文字、无水印",
        "3. 影棚级布光，柔和阴影，商品颜色与描述一致",
        "4. 正方形构图，1024×1024",
        "5. 不要出现人物、手部、品牌 logo、促销文案",
    ]
    return "\n".join(lines)
