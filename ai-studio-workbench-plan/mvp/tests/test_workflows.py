from __future__ import annotations

from pathlib import Path

from studio.config import load_config
from studio.gateway import Gateway
from studio.qa import QAChecker
from studio.store import Store
from studio.workflows.ecommerce import load_skus, run_ecommerce
from studio.workflows.short_drama import load_script, run_short_drama

ROOT = Path(__file__).resolve().parents[1]


def make_runtime(tmp_path: Path):
    config = load_config(tmp_path / "missing.yaml")
    config["data_dir"] = str(tmp_path / "data")
    store = Store(config["data_dir"])
    gateway = Gateway(config, store)
    return store, gateway, QAChecker(config.get("qa") or {})


def test_ecommerce_batch_produces_assets_and_qa(tmp_path: Path) -> None:
    store, gateway, qa = make_runtime(tmp_path)
    skus = load_skus(ROOT / "examples" / "skus.csv")[:2]
    manifest = run_ecommerce(store, gateway, qa, skus, templates=("main", "scene"))

    assert manifest["skus"] == 2
    assert len(manifest["assets"]) == 4
    assert all(item["passed"] for item in manifest["qa"])
    assert manifest["total_cost"] == 4 * 0.06
    assert manifest["stopped_reason"] == ""
    assert (store.run_dir(manifest["run_id"]) / "report.md").exists()


def test_short_drama_storyboard_keyframes_and_preview(tmp_path: Path) -> None:
    store, gateway, qa = make_runtime(tmp_path)
    script = load_script(ROOT / "examples" / "script.md")
    manifest = run_short_drama(store, gateway, qa, script)

    assert len(manifest["shots"]) == 6
    assert all(item["passed"] for item in manifest["qa"])
    assert manifest["total_cost"] == round(0.002 + 6 * 0.06, 6)
    run_dir = store.run_dir(manifest["run_id"])
    assert (run_dir / "preview.html").exists()
    assert (run_dir / "preview.json").exists()
