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
