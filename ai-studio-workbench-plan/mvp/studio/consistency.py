"""Consistency packs and prompt builders for SKU / character workflows."""

from __future__ import annotations

import hashlib
import re
from typing import Any

from studio.models import ReferencePack


def stable_seed(text: str) -> int:
    return int(hashlib.sha256(text.encode("utf-8")).hexdigest()[:8], 16)


def _slug(text: str) -> str:
    text = re.sub(r"[^0-9a-zA-Z一-鿿_-]+", "-", text.strip())
    return text.strip("-")[:40] or "item"


def ecommerce_reference_pack(sku: dict[str, Any]) -> ReferencePack:
    sku_id = str(sku.get("sku") or sku.get("id") or "SKU")
    color = str(sku.get("color") or "#cccccc")
    material = str(sku.get("material") or "未知材质")
    scene = str(sku.get("scene") or "简洁背景")
    prompt = (
        f"商品 {sku_id}，颜色 {color}，材质 {material}，"
        f"保持商品形状、颜色、logo 与包装一致，{scene}"
    )
    return ReferencePack(
        id=f"sku-{_slug(sku_id)}",
        kind="sku",
        name=sku_id,
        prompt=prompt,
        seed=stable_seed(f"sku:{sku_id}:{color}:{material}"),
        color=color,
        forbidden=["变形", "串色", "错误 logo", "多余文字"],
        metadata={"sku": sku_id, "material": material, "scene": scene},
    )


def ecommerce_prompt(sku: dict[str, Any], template: str) -> str:
    sku_id = str(sku.get("sku") or "SKU")
    color = str(sku.get("color") or "商品原色")
    material = str(sku.get("material") or "原材质")
    scene = str(sku.get("scene") or "简洁背景")
    base = (
        f"电商素材，商品 {sku_id}，颜色 {color}，材质 {material}。"
        f"严格保持商品形状、颜色、logo、包装文字不变。"
    )
    templates = {
        "main": "纯色/浅渐变背景，主体居中，商业摄影，柔和棚拍光，高清细节。",
        "scene": f"{scene}，生活方式场景，自然光，商品为视觉中心，真实阴影与反射。",
        "detail": "商品细节特写，材质纹理清晰，浅景深，干净背景。",
    }
    return base + templates.get(template, templates["main"])


def character_reference_pack(name: str, look: str) -> ReferencePack:
    return ReferencePack(
        id=f"char-{_slug(name)}",
        kind="character",
        name=name,
        prompt=f"角色 {name}：{look}。保持脸型、发型、服装、年龄一致。",
        seed=stable_seed(f"character:{name}:{look}"),
        color="#3b82f6",
        forbidden=["换脸", "换装", "年龄变化", "多余角色"],
        metadata={"character": name, "look": look},
    )


def shot_prompt(character_name: str, look: str, shot: dict[str, Any]) -> str:
    return (
        f"短剧镜头 {shot.get('shot_id', '')}。角色 {character_name}：{look}。"
        f"场景：{shot.get('scene', '')}；景别：{shot.get('shot_size', '')}；"
        f"机位：{shot.get('camera', '')}；动作：{shot.get('action', '')}；"
        f"台词：{shot.get('dialogue') or '无'}。"
        "电影感构图，人物身份一致，画面连贯，无字幕、无水印。"
    )
