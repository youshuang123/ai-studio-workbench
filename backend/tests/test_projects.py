def test_health_endpoint(client):
    resp = client.get("/api/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["t2i_configured"] is False


def test_create_project(client):
    resp = client.post("/api/projects", json={"name": "测试店铺"})
    assert resp.status_code == 201
    body = resp.json()
    assert body["name"] == "测试店铺"
    assert body["id"]


def test_create_project_empty_name(client):
    resp = client.post("/api/projects", json={"name": "   "})
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"


def test_create_project_name_too_long(client):
    resp = client.post("/api/projects", json={"name": "字" * 101})
    assert resp.status_code == 422


def test_list_projects_newest_first(client):
    first = client.post("/api/projects", json={"name": "第一个"}).json()
    second = client.post("/api/projects", json={"name": "第二个"}).json()
    body = client.get("/api/projects").json()
    assert body["total"] == 2
    assert body["items"][0]["id"] == second["id"]
    assert body["items"][1]["id"] == first["id"]
    assert body["items"][0]["asset_count"] == 0


def test_get_project_not_found(client):
    resp = client.get("/api/projects/not-exist")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "NOT_FOUND"


def test_project_detail_contains_assets(client, make_asset):
    pid, asset = make_asset()
    body = client.get(f"/api/projects/{pid}").json()
    assert body["id"] == pid
    assert len(body["assets"]) == 1
    assert body["assets"][0]["id"] == asset["id"]


def test_usage_empty(client, make_project):
    pid = make_project()["id"]
    body = client.get(f"/api/projects/{pid}/usage").json()
    assert body["total_fen"] == 0
    assert body["images"] == 0
    assert body["by_model"] == []
