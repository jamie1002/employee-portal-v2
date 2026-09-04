"""當日備註：文字由伺服器端寫死，不接受前端傳入。"""

from app.services.attendance import NOTE_PERSONAL_BUSINESS
from tests.helpers import login_headers


async def test_note_without_attendance_record_returns_400(client):
    headers = await login_headers(client, "employee@demo.com")

    response = await client.post("/api/attendance/today/note", headers=headers)

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "NO_ATTENDANCE_TODAY"


async def test_note_writes_fixed_text_onto_today_record(client):
    headers = await login_headers(client, "employee@demo.com")
    await client.post("/api/attendance/punch-in", headers=headers)

    response = await client.post("/api/attendance/today/note", headers=headers)

    assert response.status_code == 200
    assert response.json()["attendance"]["note"] == NOTE_PERSONAL_BUSINESS


async def test_note_ignores_any_text_sent_by_the_client(client):
    headers = await login_headers(client, "employee@demo.com")
    await client.post("/api/attendance/punch-in", headers=headers)

    response = await client.post(
        "/api/attendance/today/note", headers=headers, json={"note": "<script>alert(1)</script>"}
    )

    assert response.json()["attendance"]["note"] == NOTE_PERSONAL_BUSINESS
