import pytest

from app.services.prompt import NEGATIVE_PROMPT, build_prompt


def test_prompt_only_product_name():
    text = build_prompt("保温杯")
    assert "商品：保温杯" in text
    assert "类目：" not in text
    assert "卖点：" not in text
    assert "主色：" not in text
    assert "\n\n\n" not in text


def test_prompt_all_fields():
    text = build_prompt(
        "保温杯",
        category="家居",
        selling_points="24 小时保温，316 不锈钢",
        color="雾霾蓝",
    )
    assert "类目：家居" in text
    assert "卖点：24 小时保温，316 不锈钢" in text
    assert "主色：雾霾蓝" in text


def test_prompt_truncates_long_selling_points():
    text = build_prompt("杯子", selling_points="很" * 500)
    line = [ln for ln in text.splitlines() if ln.startswith("卖点：")][0]
    assert len(line) <= 200 + len("卖点：")


def test_negative_prompt_constant():
    assert "watermark" in NEGATIVE_PROMPT
    assert "logo" in NEGATIVE_PROMPT


def test_prompt_rejects_empty_name():
    with pytest.raises(ValueError):
        build_prompt("   ")


def test_prompt_keeps_special_characters():
    text = build_prompt("A&B <测试> \"引号\"")
    assert "A&B <测试>" in text
