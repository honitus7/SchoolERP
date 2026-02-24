def test_dashboard_and_module_pages_load_after_login(client):
    login = client.post(
        "/login",
        data={"username": "admin", "password": "admin123"},
        follow_redirects=True,
    )
    assert login.status_code == 200
    assert b"Overview" in login.data

    module = client.get("/attendance/")
    assert module.status_code == 200
    assert b"module-console" in module.data

    dashboard = client.get("/dashboard/admin")
    assert dashboard.status_code == 200
    assert b"dashboard-live" in dashboard.data
