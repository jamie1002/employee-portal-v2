"""登入與 /auth/me 的測試。"""


async def test_login_success_returns_token_and_user(client):
    response = await client.post(
        "/api/auth/login", json={"email": "admin@demo.com", "password": "Demo1234"}
    )

    assert response.status_code == 200
    body = response.json()
    assert "token" in body and body["token"]
    assert body["user"]["email"] == "admin@demo.com"
    assert body["user"]["role"] == "admin"
    assert "password_hash" not in body["user"]
    assert body["user"]["permissions"] == []


async def test_login_wrong_password_returns_generic_invalid_credentials(client):
    response = await client.post(
        "/api/auth/login", json={"email": "admin@demo.com", "password": "WrongPass1"}
    )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "INVALID_CREDENTIALS"


async def test_login_unknown_email_returns_same_error_as_wrong_password(client):
    """帳號不存在與密碼錯誤必須回傳完全相同的訊息與 code，不洩漏是哪一種情況。"""
    response = await client.post(
        "/api/auth/login", json={"email": "nobody@demo.com", "password": "WrongPass1"}
    )

    assert response.status_code == 401
    body = response.json()
    assert body["error"]["code"] == "INVALID_CREDENTIALS"

    wrong_password_response = await client.post(
        "/api/auth/login", json={"email": "admin@demo.com", "password": "WrongPass1"}
    )
    assert wrong_password_response.json()["error"]["message"] == body["error"]["message"]


async def test_get_me_without_token_returns_401_not_403(client):
    response = await client.get("/api/auth/me")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHORIZED"


async def test_get_me_with_valid_token_returns_current_user(client):
    login_response = await client.post(
        "/api/auth/login", json={"email": "employee@demo.com", "password": "Demo1234"}
    )
    token = login_response.json()["token"]

    response = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    assert response.json()["user"]["email"] == "employee@demo.com"


async def test_get_me_with_garbage_token_returns_401_invalid_token(client):
    response = await client.get("/api/auth/me", headers={"Authorization": "Bearer not-a-real-token"})

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "INVALID_TOKEN"
