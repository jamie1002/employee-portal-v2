"""骨架測試：健康檢查端點回報資料庫已連線。"""


async def test_health_check_returns_ok_and_connected(client):
    response = await client.get("/api/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["database"] == "connected"
