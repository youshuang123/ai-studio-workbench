import io

from PIL import Image


def test_upload_png_ok(client, make_project, png_bytes):
    pid = make_project()["id"]
    resp = client.post(
        f"/api/projects/{pid}/assets",
        files={"file": ("商品图.png", png_bytes, "image/png")},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["kind"] == "upload"
    assert body["width"] == 64
    assert body["height"] == 64
    assert body["bytes"] > 0
    assert body["url"].endswith("/file")


def test_upload_rejects_fake_png(client, make_project):
    pid = make_project()["id"]
    resp = client.post(
        f"/api/projects/{pid}/assets",
        files={"file": ("fake.png", b"this is not an image", "image/png")},
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "INVALID_FILE"


def test_upload_rejects_too_large(client, make_project):
    pid = make_project()["id"]
    huge = b"\x00" * (11 * 1024 * 1024)
    resp = client.post(
        f"/api/projects/{pid}/assets",
        files={"file": ("big.png", huge, "image/png")},
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "FILE_TOO_LARGE"


def test_upload_rejects_mismatched_extension(client, make_project, png_bytes):
    pid = make_project()["id"]
    resp = client.post(
        f"/api/projects/{pid}/assets",
        files={"file": ("image.jpg", png_bytes, "image/png")},
    )
    assert resp.status_code == 400
    assert "扩展名" in resp.json()["error"]["message"]


def test_upload_path_traversal_filename_is_ignored(client, make_project, png_bytes):
    pid = make_project()["id"]
    resp = client.post(
        f"/api/projects/{pid}/assets",
        files={"file": ("../../etc/passwd.png", png_bytes, "image/png")},
    )
    assert resp.status_code == 201
    body = resp.json()

    from app import config
    from app.db import SessionLocal
    from app import models

    db = SessionLocal()
    try:
        asset = db.get(models.Asset, body["id"])
        assert asset is not None
        full = (config.ASSETS_DIR / asset.path).resolve()
        assert str(full).startswith(str(config.ASSETS_DIR.resolve()))
        assert ".." not in asset.path
        assert full.exists()
    finally:
        db.close()


def test_get_asset_file(client, make_asset):
    _, asset = make_asset()
    resp = client.get(f"/api/assets/{asset['id']}/file")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("image/png")
    assert Image.open(io.BytesIO(resp.content)).size == (64, 64)


def test_download_sets_attachment(client, make_asset):
    _, asset = make_asset(filename="商品主图.png")
    resp = client.get(f"/api/assets/{asset['id']}/download")
    assert resp.status_code == 200
    assert "attachment" in resp.headers.get("content-disposition", "")


def test_get_asset_not_found(client):
    resp = client.get("/api/assets/not-exist/file")
    assert resp.status_code == 404


def test_upload_to_missing_project(client, png_bytes):
    resp = client.post(
        "/api/projects/not-exist/assets",
        files={"file": ("a.png", png_bytes, "image/png")},
    )
    assert resp.status_code == 404
