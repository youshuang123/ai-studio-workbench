from typing import Any

from pydantic import BaseModel, Field, field_validator


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    description: str = Field(default="", max_length=500)

    @field_validator("name")
    @classmethod
    def _strip_name(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("项目名称不能为空")
        return v

    @field_validator("description")
    @classmethod
    def _strip_desc(cls, v: str) -> str:
        return v.strip()


class ProjectOut(BaseModel):
    id: str
    name: str
    description: str
    created_at: str | None = None


class ProjectListItem(BaseModel):
    id: str
    name: str
    asset_count: int
    job_count: int
    created_at: str | None = None


class ProjectListOut(BaseModel):
    items: list[ProjectListItem]
    total: int


class AssetOut(BaseModel):
    id: str
    project_id: str
    kind: str
    filename: str
    mime: str
    bytes: int
    width: int
    height: int
    created_at: str | None = None
    url: str = ""


class ProjectDetailOut(BaseModel):
    id: str
    name: str
    description: str
    created_at: str | None = None
    assets: list[AssetOut] = Field(default_factory=list)
    recent_jobs: list[dict[str, Any]] = Field(default_factory=list)


class GenerationCreate(BaseModel):
    source_asset_id: str = Field(min_length=1, max_length=36)
    product_name: str = Field(min_length=1, max_length=50)
    category: str = Field(default="", max_length=50)
    selling_points: str = Field(default="", max_length=200)
    color: str = Field(default="", max_length=20)
    budget_cny: float | None = Field(default=None, gt=0, le=100)

    @field_validator("product_name")
    @classmethod
    def _strip_product(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("商品名称不能为空")
        return v

    @field_validator("category", "selling_points", "color")
    @classmethod
    def _strip_optional(cls, v: str) -> str:
        return v.strip()


class GenerationOut(BaseModel):
    id: str
    project_id: str
    status: str
    product_name: str
    output_asset_id: str | None = None
    cost_fen: int
    unit_price_fen: int
    elapsed_ms: int | None = None
    error_code: str = ""
    error_message: str = ""
    created_at: str | None = None


class UsageOut(BaseModel):
    total_fen: int
    images: int
    by_model: list[dict[str, Any]] = Field(default_factory=list)
