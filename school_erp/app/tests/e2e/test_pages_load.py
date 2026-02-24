
def test_login_page_loads(client):
    response = client.get("/login")
    assert response.status_code == 200
    assert b"School ERP Platform" in response.data
