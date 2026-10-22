"""测试基座：所有测试用临时数据库 + 临时数据目录，不碰真实数据、不调真实模型。"""

import os
import tempfile

_TMP = tempfile.mkdtemp(prefix="aistudio-test-")
os.environ["DATABASE_URL"] = f"sqlite:///{_TMP}/test.db"
os.environ["DATA_DIR"] = _TMP
os.environ["MODEL_T2I_API_KEY"] = ""
os.environ["MODEL_T2I_UNIT_PRICE"] = "0.03"
os.environ["TASK_BUDGET_CNY"] = "5.00"

import io  # noqa: E402

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from PIL import Image  # noqa: E402

from app.db import Base, engine  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture(autouse=True)
def clean_db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture
def png_bytes():
    buf = io.BytesIO()
    Image.new("RGB", (64, 64), (200, 30, 30)).save(buf, format="PNG")
    return buf.getvalue()


@pytest.fixture
def make_project(client):
    def _make(name="测试项目"):
        resp = client.post("/api/projects", json={"name": name})
        assert resp.status_code == 201, resp.text
        return resp.json()

    return _make


@pytest.fixture
def make_asset(client, make_project, png_bytes):
    def _make(project_id=None, filename="product.png"):
        pid = project_id or make_project()["id"]
        resp = client.post(
            f"/api/projects/{pid}/assets",
            files={"file": (filename, png_bytes, "image/png")},
        )
        assert resp.status_code == 201, resp.text
        return pid, resp.json()

    return _make
