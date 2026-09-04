import { useState } from "react";
import { formatDateTime as formatDateTimeBase } from "../utils/datetime";
import RequestStatusBadge from "./RequestStatusBadge";

const formatDateTime = (isoString) => formatDateTimeBase(isoString, { withYear: true });

// 狀態欄位可點擊展開，顯示送出時間、審核者姓名、審核時間、駁回備註——這些欄位
// 本來就存在於三張申請單表，這裡純粹是前端呈現，不需要新增後端邏輯。
export default function RequestStatusCell({ request }) {
  const [expanded, setExpanded] = useState(false);

  return (
    <div>
      <button type="button" onClick={() => setExpanded((prev) => !prev)} className="flex items-center gap-1 text-left">
        <RequestStatusBadge status={request.status} />
        <span className="text-xs text-text-muted">{expanded ? "收合 ▲" : "詳情 ▼"}</span>
      </button>

      {expanded && (
        <dl className="mt-2 space-y-1 text-xs text-text-secondary">
          <div className="flex gap-2">
            <dt className="text-text-muted">送出時間：</dt>
            <dd>{formatDateTime(request.created_at)}</dd>
          </div>
          {request.status !== "pending" && (
            <>
              <div className="flex gap-2">
                <dt className="text-text-muted">審核者：</dt>
                <dd>{request.reviewer_name ?? "—"}</dd>
              </div>
              <div className="flex gap-2">
                <dt className="text-text-muted">審核時間：</dt>
                <dd>{formatDateTime(request.reviewed_at)}</dd>
              </div>
              {request.status === "rejected" && (
                <div className="flex gap-2">
                  <dt className="text-text-muted">駁回備註：</dt>
                  <dd>{request.review_note ?? "—"}</dd>
                </div>
              )}
            </>
          )}
        </dl>
      )}
    </div>
  );
}
