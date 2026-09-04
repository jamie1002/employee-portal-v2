"""細粒度權限下放的測試（見 SPEC.md §3.4、§8.1）。"""

import asyncio


async def _login(client, email, password="Demo1234"):
    response = await client.post("/api/auth/login", json={"email": email, "password": password})
    return response.json()["token"]


async def _admin_token(client):
    return await _login(client, "admin@demo.com")


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


async def test_list_permissions_includes_seeded_grant(client):
    token = await _admin_token(client)

    response = await client.get("/api/users/permissions", headers=_auth(token))

    assert response.status_code == 200
    rows = response.json()["permissions"]
    seeded = next(row for row in rows if row["user_id"] == 6 and row["permission"] == "holidays.manage")
    assert seeded["granted_by_name"] == "系統管理者"


async def test_non_admin_cannot_list_or_set_permissions(client):
    token = await _login(client, "employee@demo.com")

    list_response = await client.get("/api/users/permissions", headers=_auth(token))
    assert list_response.status_code == 403
    assert list_response.json()["error"]["code"] == "FORBIDDEN"

    set_response = await client.put(
        "/api/users/3/permissions", json={"permissions": ["exports.run"]}, headers=_auth(token)
    )
    assert set_response.status_code == 403
    assert set_response.json()["error"]["code"] == "FORBIDDEN"


async def test_cannot_grant_permission_to_admin(client):
    token = await _admin_token(client)

    response = await client.put(
        "/api/users/1/permissions", json={"permissions": ["exports.run"]}, headers=_auth(token)
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "ADMIN_PERMISSIONS_IMPLICIT"


async def test_granting_to_nonexistent_user_returns_404(client):
    token = await _admin_token(client)

    response = await client.put(
        "/api/users/999999/permissions", json={"permissions": ["exports.run"]}, headers=_auth(token)
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


async def test_invalid_permission_key_is_rejected(client):
    token = await _admin_token(client)

    response = await client.put(
        "/api/users/5/permissions", json={"permissions": ["not.a.real.permission"]}, headers=_auth(token)
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


async def test_permission_takes_effect_and_is_revoked_immediately_on_same_token(client):
    """釘住「權限不在 JWT 裡」：同一個舊 token，授權後立即可用、收回後立即被擋
    （見 docs/PITFALLS.md C3）。用 GET /auth/me 的即時重查間接驗證，
    因為批 1 還沒有其他掛 require_permission 的業務端點。"""
    admin_token = await _admin_token(client)
    employee_token = await _login(client, "chang@demo.com")

    before = await client.get("/api/auth/me", headers=_auth(employee_token))
    assert before.json()["user"]["permissions"] == []

    grant_response = await client.put(
        "/api/users/5/permissions", json={"permissions": ["exports.run"]}, headers=_auth(admin_token)
    )
    assert grant_response.status_code == 200

    after_grant = await client.get("/api/auth/me", headers=_auth(employee_token))
    assert after_grant.json()["user"]["permissions"] == ["exports.run"]

    revoke_response = await client.put(
        "/api/users/5/permissions", json={"permissions": []}, headers=_auth(admin_token)
    )
    assert revoke_response.status_code == 200

    after_revoke = await client.get("/api/auth/me", headers=_auth(employee_token))
    assert after_revoke.json()["user"]["permissions"] == []


async def test_partial_update_preserves_granted_by_and_granted_at(client):
    """權限整組取代時，未變動的權限其 granted_by／granted_at 必須不變——
    服務層是 diff 實作，不是「先刪光再全部插入」（見 docs/PITFALLS.md C5）。"""
    admin_token = await _admin_token(client)

    first = await client.put(
        "/api/users/4/permissions",
        json={"permissions": ["exports.run", "settings.manage"]},
        headers=_auth(admin_token),
    )
    assert first.status_code == 200
    first_rows = {row["permission"]: row for row in first.json()["permissions"]}
    original_granted_at = first_rows["exports.run"]["granted_at"]

    # 真實時間流逝一段可觀察的間隔，若程式碼是「刪光重建」，granted_at 會被洗成更晚的時間。
    await asyncio.sleep(1.2)

    second = await client.put(
        "/api/users/4/permissions",
        json={"permissions": ["exports.run"]},
        headers=_auth(admin_token),
    )
    assert second.status_code == 200
    second_rows = {row["permission"]: row for row in second.json()["permissions"]}

    assert "settings.manage" not in second_rows
    assert second_rows["exports.run"]["granted_at"] == original_granted_at
    assert second_rows["exports.run"]["granted_by"] == 1
