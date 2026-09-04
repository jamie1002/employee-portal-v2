"""匯出報表端點（SPEC.md §4.8 §6.7）。

`roles` 參數絕對不能省略——寫成 `require_permission("exports.run")` 會套用
預設的 `roles=("admin",)`，直接砍掉現有 manager 的匯出權（見 docs/PITFALLS.md C4）。
"""

from fastapi import APIRouter, Depends, Request, Response

from app.config.database import get_pool
from app.middleware.auth import require_permission
from app.schemas.export import parse_export_kind, parse_export_request
from app.services import export as export_service

router = APIRouter()


@router.post("/exports/{kind}")
async def export_data(
    kind: str,
    request: Request,
    current_user: dict = Depends(require_permission("exports.run", roles=("admin", "manager"))),
):
    parsed_kind = parse_export_kind(kind)
    body = await request.json()
    data = parse_export_request(parsed_kind, body)

    if request.query_params.get("format") == "xlsx":
        content = await export_service.build_export_xlsx(
            get_pool(), parsed_kind, data["filters"], data["columns"], current_user
        )
        return Response(
            content=content,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f'attachment; filename="{parsed_kind}.xlsx"'},
        )

    return await export_service.get_export_preview(
        get_pool(), parsed_kind, data["filters"], data["columns"], current_user
    )
