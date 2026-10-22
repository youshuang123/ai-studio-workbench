"""Command-line entry point.

Usage:
  python -m studio demo
  python -m studio ecommerce --skus examples/skus.csv
  python -m studio drama --script examples/script.md
  python -m studio cost --image-price 0.06 --video-price-5s 0.10
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from studio.config import data_dir, load_config
from studio.cost import CostAssumptions, image_cost, i2v_minute_cost, light_motion_cost
from studio.gateway import Budget, Gateway
from studio.qa import QAChecker
from studio.store import Store
from studio.workflows.ecommerce import load_skus, run_ecommerce
from studio.workflows.short_drama import load_script, run_short_drama

ROOT = Path(__file__).resolve().parents[1]


def _configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )


def build_runtime(config: dict, max_cost: float | None = None):
    if max_cost is not None:
        config.setdefault("budget", {})["max_cost_per_run"] = float(max_cost)
    store = Store(data_dir(config))
    gateway = Gateway(config, store)
    qa = QAChecker(config.get("qa") or {})
    return store, gateway, qa


def _print_summary(manifest: dict, run_dir: Path) -> None:
    print("\n" + "=" * 60)
    print(f"run_id: {manifest['run_id']}")
    print(f"type:   {manifest['type']}")
    print(f"cost:   ¥{manifest['total_cost']:.4f} {manifest.get('currency', 'CNY')}")
    if manifest.get("stopped_reason"):
        print(f"stop:   {manifest['stopped_reason']}")
    if manifest.get("errors"):
        print(f"errors: {len(manifest['errors'])}")
    print(f"dir:    {run_dir}")
    if manifest["type"] == "ecommerce":
        print(f"assets: {len(manifest['assets'])}")
        print(f"report: {run_dir / 'report.md'}")
    else:
        print(f"shots:  {len(manifest['shots'])}")
        print(f"report: {run_dir / 'report.md'}")
        print(f"preview:{run_dir / 'preview.html'}")
    print("=" * 60)


def cmd_demo(args) -> int:
    config = load_config(args.config)
    if args.out:
        config["data_dir"] = args.out
    store, gateway, qa = build_runtime(config, args.max_cost)

    skus_path = Path(args.skus) if args.skus else ROOT / "examples" / "skus.csv"
    script_path = Path(args.script) if args.script else ROOT / "examples" / "script.md"

    print("1/2 电商素材工作流（mock API，离线）")
    ecom = run_ecommerce(store, gateway, qa, load_skus(skus_path))
    _print_summary(ecom, store.run_dir(ecom["run_id"]))

    print("\n2/2 短剧工作流（mock API，离线）")
    drama_store, drama_gateway, drama_qa = build_runtime(config, args.max_cost)
    drama = run_short_drama(
        drama_store, drama_gateway, drama_qa, load_script(script_path)
    )
    _print_summary(drama, drama_store.run_dir(drama["run_id"]))
    return 0


def cmd_ecommerce(args) -> int:
    config = load_config(args.config)
    if args.out:
        config["data_dir"] = args.out
    store, gateway, qa = build_runtime(config, args.max_cost)
    templates = tuple(t.strip() for t in args.templates.split(",") if t.strip())
    manifest = run_ecommerce(
        store, gateway, qa, load_skus(args.skus), templates=templates or ("main", "scene")
    )
    _print_summary(manifest, store.run_dir(manifest["run_id"]))
    return 0


def cmd_drama(args) -> int:
    config = load_config(args.config)
    if args.out:
        config["data_dir"] = args.out
    store, gateway, qa = build_runtime(config, args.max_cost)
    manifest = run_short_drama(
        store, gateway, qa, load_script(args.script),
        character_name=args.character, look=args.look,
    )
    _print_summary(manifest, store.run_dir(manifest["run_id"]))
    return 0


def cmd_cost(args) -> int:
    assumptions = CostAssumptions()
    print("成本测算（示例假设，按你的 API 报价修改）")
    print(f"重试率 {assumptions.retry_rate:.0%}，缓存命中 {assumptions.cache_hit:.0%}")
    print(f"目标：图片 ≤ ¥{assumptions.target_image:.2f}/张；"
          f"视频 ≤ ¥{assumptions.target_video_minute:.2f}/分钟\n")

    print("== 图片 ==")
    for price in (0.03, 0.05, 0.06, 0.08, 0.10, 0.15, 0.30):
        cost = image_cost(price, assumptions)
        mark = "✅" if cost <= assumptions.target_image else "❌"
        print(f"  API ¥{price:.2f}/张 → ¥{cost:.4f}/张 {mark}")

    print("\n== 视频 ==")
    motion = light_motion_cost(assumptions)
    print(f"  关键帧 + 轻动效：¥{motion:.4f}/分钟 "
          f"{'✅' if motion <= assumptions.target_video_minute else '❌'}")
    for price in (0.03, 0.05, 0.08, 0.10, 0.30, 1.00):
        cost = i2v_minute_cost(price, assumptions)
        mark = "✅" if cost <= assumptions.target_video_minute else "❌"
        print(f"  完整 I2V API ¥{price:.2f}/5秒 → ¥{cost:.2f}/分钟 {mark}")
    print("\n结论：¥0.10/张可行；¥1/分钟完整 I2V 基本不可行，MVP 用轻动效。")
    return 0


def cmd_inspect(args) -> int:
    manifest_path = Path(args.run) / "manifest.json"
    if not manifest_path.exists():
        print(f"manifest not found: {manifest_path}", file=sys.stderr)
        return 1
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    shot_assets = [shot for shot in data.get("shots", []) if shot.get("asset")]
    print(json.dumps(
        {
            "run_id": data.get("run_id"),
            "type": data.get("type"),
            "total_cost": data.get("total_cost"),
            "assets": len(data.get("assets", [])) + len(shot_assets),
            "shots": len(data.get("shots", [])),
            "stopped_reason": data.get("stopped_reason"),
            "errors": data.get("errors", []),
        },
        ensure_ascii=False,
        indent=2,
    ))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="studio", description="AI Studio MVP skeleton")
    parser.add_argument("--config", help="config.yaml path")
    sub = parser.add_subparsers(dest="cmd", required=True)

    def common(sp):
        sp.add_argument("--out", help="data directory (default: data)")
        sp.add_argument("--max-cost", type=float, help="override max cost per run")

    sp = sub.add_parser("demo", help="run both workflows offline with mock API")
    sp.add_argument("--skus", help="SKU CSV path")
    sp.add_argument("--script", help="short-drama script path")
    common(sp)
    sp.set_defaults(func=cmd_demo)

    sp = sub.add_parser("ecommerce", help="run e-commerce batch workflow")
    sp.add_argument("--skus", required=True, help="SKU CSV path")
    sp.add_argument("--templates", default="main,scene", help="comma-separated templates")
    common(sp)
    sp.set_defaults(func=cmd_ecommerce)

    sp = sub.add_parser("drama", help="run short-drama workflow")
    sp.add_argument("--script", required=True, help="script path")
    sp.add_argument("--character", default="小夏")
    sp.add_argument("--look", default="20 岁，短发，米色风衣，透明雨伞")
    common(sp)
    sp.set_defaults(func=cmd_drama)

    sp = sub.add_parser("cost", help="print cost targets")
    sp.set_defaults(func=cmd_cost)

    sp = sub.add_parser("inspect", help="inspect a run manifest")
    sp.add_argument("run", help="run directory")
    sp.set_defaults(func=cmd_inspect)
    return parser


def main(argv: list[str] | None = None) -> None:
    _configure_logging()
    args = build_parser().parse_args(argv)
    try:
        sys.exit(args.func(args))
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"\n⛔ {exc}", file=sys.stderr)
        sys.exit(1)
