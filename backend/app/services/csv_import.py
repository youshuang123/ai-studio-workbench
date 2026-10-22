"""CSV 导入与逐行校验（纯函数，重点单测）。

规则（2-2 技术开发文档 §6.4）：
- 表头固定：sku_code, product_name, category, color, selling_points, image_file
- sku_code 必填且批次内唯一；product_name 必填
- 编码：UTF-8-sig 优先，失败回退 GBK，都失败报错
- 缺图行 → skipped，不阻断其他行
- 行数上限 200
"""

import csv
import io
from dataclasses import dataclass, field

MAX_ROWS = 200

REQUIRED_HEADERS = ["sku_code", "product_name"]
ALL_HEADERS = [
    "sku_code",
    "product_name",
    "category",
    "color",
    "selling_points",
    "image_file",
]

# 字段长度上限（与 schemas.GenerationCreate 保持一致）
LIMITS = {
    "sku_code": 40,
    "product_name": 50,
    "category": 50,
    "color": 20,
    "selling_points": 200,
    "image_file": 255,
}


class CsvError(Exception):
    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message
        super().__init__(message)


@dataclass
class Row:
    index: int  # 1-based 数据行号（不含表头）
    sku_code: str = ""
    product_name: str = ""
    category: str = ""
    color: str = ""
    selling_points: str = ""
    image_file: str = ""
    ok: bool = True
    skipped: bool = False
    errors: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "index": self.index,
            "sku_code": self.sku_code,
            "product_name": self.product_name,
            "category": self.category,
            "color": self.color,
            "selling_points": self.selling_points,
            "image_file": self.image_file,
            "ok": self.ok,
            "skipped": self.skipped,
            "errors": self.errors,
        }


@dataclass
class ParseResult:
    rows: list[Row]
    errors: list[dict]
    missing_images: list[dict]

    @property
    def total(self) -> int:
        return len(self.rows)

    @property
    def valid(self) -> int:
        return len([r for r in self.rows if r.ok and not r.skipped])

    def to_dict(self) -> dict:
        return {
            "rows": [r.to_dict() for r in self.rows],
            "errors": self.errors,
            "missing_images": self.missing_images,
            "total": self.total,
            "valid": self.valid,
        }


def decode(raw: bytes) -> str:
    """UTF-8-sig → UTF-8 → GBK 依次尝试。"""
    for encoding in ("utf-8-sig", "utf-8", "gbk"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise CsvError(
        "CSV_ENCODING",
        "文件编码无法识别，请用 Excel「另存为」选择 UTF-8 或 GB18030 后再上传",
    )


def parse(raw: bytes, existing_filenames: set[str] | None = None) -> ParseResult:
    """解析并校验 CSV。existing_filenames 用于判断「缺图」。"""
    text = decode(raw)
    reader = csv.DictReader(io.StringIO(text))

    if reader.fieldnames is None:
        raise CsvError("CSV_EMPTY", "文件是空的，或者没有表头")

    headers = [h.strip() for h in reader.fieldnames if h]
    missing_required = [h for h in REQUIRED_HEADERS if h not in headers]
    if missing_required:
        raise CsvError(
            "CSV_HEADER",
            f"缺少必需的表头：{', '.join(missing_required)}。"
            f"请使用示例表的格式：{', '.join(ALL_HEADERS)}",
        )

    rows: list[Row] = []
    errors: list[dict] = []
    missing_images: list[dict] = []
    seen_skus: dict[str, int] = {}

    for i, raw_row in enumerate(reader, start=1):
        if i > MAX_ROWS:
            raise CsvError(
                "CSV_TOO_MANY_ROWS",
                f"一次最多 {MAX_ROWS} 行，当前文件超过上限，请拆分后再上传",
            )

        if not any((v or "").strip() for v in raw_row.values() if isinstance(v, str)):
            continue  # 跳过完全空行

        row = Row(index=len(rows) + 1)
        row_errors: list[dict] = []

        for key in ALL_HEADERS:
            value = (raw_row.get(key) or "").strip()
            limit = LIMITS.get(key)
            if limit and len(value) > limit:
                row_errors.append(
                    {
                        "row": row.index,
                        "column": key,
                        "message": f"超过 {limit} 个字（当前 {len(value)}）",
                    }
                )
                value = value[:limit]
            setattr(row, key, value)

        if not row.sku_code:
            row_errors.append(
                {"row": row.index, "column": "sku_code", "message": "SKU 编码不能为空"}
            )
        elif row.sku_code in seen_skus:
            row_errors.append(
                {
                    "row": row.index,
                    "column": "sku_code",
                    "message": f"SKU 编码重复：{row.sku_code}（第 {seen_skus[row.sku_code]} 行已使用）",
                }
            )
        else:
            seen_skus[row.sku_code] = row.index

        if not row.product_name:
            row_errors.append(
                {"row": row.index, "column": "product_name", "message": "商品名称不能为空"}
            )

        if row_errors:
            row.ok = False
            row.errors = row_errors
            errors.extend(row_errors)

        # 缺图只标记 skipped，不阻断其他行
        if row.ok and row.image_file and existing_filenames is not None:
            if row.image_file not in existing_filenames:
                row.skipped = True
                missing_images.append(
                    {
                        "row": row.index,
                        "sku_code": row.sku_code,
                        "file": row.image_file,
                    }
                )

        rows.append(row)

    if not rows:
        raise CsvError("CSV_NO_ROWS", "文件里没有任何数据行")

    return ParseResult(rows=rows, errors=errors, missing_images=missing_images)


def build_prompt_inputs(row: Row) -> dict:
    """把行数据转成生成接口需要的字段（不含 source_asset_id）。"""
    return {
        "product_name": row.product_name,
        "category": row.category,
        "selling_points": row.selling_points,
        "color": row.color,
    }
