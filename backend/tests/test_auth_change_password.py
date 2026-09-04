"""修改密碼的測試：展示帳號鎖定、舊密碼驗證、新密碼規則、不得與原密碼相同。"""


async def _login(client, email, password="Demo1234"):
    response = await client.post("/api/auth/login", json={"email": email, "password": password})
    return response.json()["token"]


async def test_demo_account_cannot_change_password(client):
    token = await _login(client, "admin@demo.com")

    response = await client.post(
        "/api/auth/change-password",
        json={"oldPassword": "Demo1234", "newPassword": "NewPass99"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "DEMO_ACCOUNT_PASSWORD_LOCKED"


async def test_wrong_old_password_is_rejected(client):
    token = await _login(client, "chang@demo.com")

    response = await client.post(
        "/api/auth/change-password",
        json={"oldPassword": "WrongOld1", "newPassword": "NewPass99"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "INVALID_OLD_PASSWORD"


async def test_new_password_must_meet_complexity_rule(client):
    token = await _login(client, "chang@demo.com")

    response = await client.post(
        "/api/auth/change-password",
        json={"oldPassword": "Demo1234", "newPassword": "alllettersnodigits"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


async def test_new_password_same_as_old_is_rejected(client):
    token = await _login(client, "chang@demo.com")

    response = await client.post(
        "/api/auth/change-password",
        json={"oldPassword": "Demo1234", "newPassword": "Demo1234"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "PASSWORD_UNCHANGED"


async def test_successful_change_allows_login_with_new_password_only(client):
    token = await _login(client, "lin@demo.com")

    response = await client.post(
        "/api/auth/change-password",
        json={"oldPassword": "Demo1234", "newPassword": "NewPass99"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200

    old_login = await client.post("/api/auth/login", json={"email": "lin@demo.com", "password": "Demo1234"})
    assert old_login.status_code == 401

    new_login = await client.post("/api/auth/login", json={"email": "lin@demo.com", "password": "NewPass99"})
    assert new_login.status_code == 200
