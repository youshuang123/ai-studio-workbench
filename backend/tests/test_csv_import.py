"""CSV 解析与逐行校验（纯函数，不需要起服务）。"""

import pytest

from app.services import csv_import

HEADER = "sku_code,product_name,category,color,selling_points,image_file\n"


def _csv(*rows: str, header: str = HEADER) -> bytes:
    return (header + "\n".join(rows) + "\n").encode("utf-8")


def test_parse_normal_rows():
    raw = _csv(
        "CUP-001,保温杯,家居,深蓝,24小时保温,product.png",
        "CUP-002,冷水壶,家居,透明,耐冷热,product.png",
    )
    result = csv_import.parse(raw)
    assert result.total == 2
    assert result.valid == 2
    assert result.errors == []
    assert result.rows[0].sku_code == "CUP-001"


def test_parse_utf8_bom():
    raw = ("\ufeff" + HEADER + "A-1,杯子,,,,\n").encode("utf-8")
    result = csv_import.parse(raw)
    assert result.valid == 1


def test_parse_gbk():
    text = HEADER + "A-1,保温杯,,,,\n"
    result = csv_import.parse(text.encode("gbk"))
    assert result.rows[0].product_name == "保温杯"


def test_missing_required_header():
    raw = _csv("CUP-1,杯子", header="sku_code,category\n")
    with pytest.raises(csv_import.CsvError) as exc:
        csv_import.parse(raw)
    assert exc.value.code == "CSV_HEADER"
    assert "product_name" in exc.value.message


def test_empty_product_name_is_row_error():
    raw = _csv("CUP-1,,家居,,")
    result = csv_import.parse(raw)
    assert result.valid == 0
    assert any(e["column"] == "product_name" for e in result.errors)
    assert result.rows[0].ok is False


def test_duplicate_sku_is_row_error():
    raw = _csv("CUP-1,杯子,,,", "CUP-1,另一个杯子,,,")
    result = csv_import.parse(raw)
    assert result.valid == 1
    dup = [e for e in result.errors if e["column"] == "sku_code"]
    assert dup and "重复" in dup[0]["message"]
    assert dup[0]["row"] == 2


def test_long_field_is_truncated_and_reported():
    raw = _csv("CUP-1," + "字" * 80 + ",,,")
    result = csv_import.parse(raw)
    assert len(result.rows[0].product_name) == 50
    assert any("超过 50" in e["message"] for e in result.errors)


def test_too_many_rows():
    rows = [f"CUP-{i},杯子{i},,," for i in range(201)]
    with pytest.raises(csv_import.CsvError) as exc:
        csv_import.parse(_csv(*rows))
    assert exc.value.code == "CSV_TOO_MANY_ROWS"


def test_missing_image_marks_skipped_not_error():
    raw = _csv("CUP-1,杯子,,,,product.png", "CUP-2,杯子2,,,,nope.png")
    result = csv_import.parse(raw, existing_filenames={"product.png"})
    assert result.total == 2        # 两行都解析出来了
    assert result.valid == 1        # 但只有 1 行可执行（缺图行算跳过）
    assert result.rows[1].skipped is True
    assert result.missing_images[0]["file"] == "nope.png"


def test_no_data_rows():
    with pytest.raises(csv_import.CsvError) as exc:
        csv_import.parse(HEADER.encode("utf-8"))
    assert exc.value.code == "CSV_NO_ROWS"


def test_blank_lines_are_ignored():
    raw = _csv("CUP-1,杯子,,,", "", "  ,  ,  ,  ,", "CUP-2,杯子2,,,")
    result = csv_import.parse(raw)
    assert result.total == 2


def test_build_prompt_inputs():
    raw = _csv("CUP-1,保温杯,家居,深蓝,保温")
    row = csv_import.parse(raw).rows[0]
    inputs = csv_import.build_prompt_inputs(row)
    assert inputs["product_name"] == "保温杯"
    assert inputs["color"] == "深蓝"
    assert "sku_code" not in inputs
