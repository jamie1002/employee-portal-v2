"""場地清單端點。"""

from fastapi import APIRouter, Depends

from app.config.database import get_pool
from app.middleware.auth import get_current_user
from app.repositories import room_repository

router = APIRouter()


@router.get("/rooms")
async def get_rooms(current_user: dict = Depends(get_current_user)):
    rooms = await room_repository.find_all(get_pool())
    return {"rooms": [dict(row) for row in rooms]}
