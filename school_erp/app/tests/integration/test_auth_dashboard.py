def auth_header(token):
    return {"Authorization": f"Bearer {token}"}


def test_login_and_dashboard_flow(client):
    login = client.post(
        "/api/v1/auth/login",
        json={"username": "admin", "password": "admin123"},
    )
    assert login.status_code == 200
    token = login.json["data"]["tokens"]["access"]

    dashboard = client.get("/api/v1/dashboard/admin", headers=auth_header(token))
    assert dashboard.status_code == 200
    data = dashboard.json["data"]
    assert data["role"] == "admin"
    assert "kpis" in data


def test_dashboard_role_scope_enforced(client):
    login = client.post("/login", data={"username": "parent", "password": "parent123"}, follow_redirects=True)
    assert login.status_code == 200

    forbidden = client.get("/dashboard/admin")
    assert forbidden.status_code == 403


def test_api_dashboard_role_scope_enforced(client):
    parent_login = client.post(
        "/api/v1/auth/login",
        json={"username": "parent", "password": "parent123"},
    )
    assert parent_login.status_code == 200
    parent_token = parent_login.json["data"]["tokens"]["access"]

    allowed = client.get("/api/v1/dashboard/parent", headers=auth_header(parent_token))
    assert allowed.status_code == 200

    forbidden = client.get("/api/v1/dashboard/admin", headers=auth_header(parent_token))
    assert forbidden.status_code == 403
