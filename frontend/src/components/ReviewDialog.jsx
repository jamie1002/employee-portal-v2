import { useState } from "react";

// 核准直接送出；駁回彈出內嵌表單要求填寫原因，未填寫時送出按鈕維持停用。
export default function ReviewDialog({ onApprove, onReject, isSubmitting = false }) {
  const [showRejectForm, setShowRejectForm] = useState(false);
  const [note, setNote] = useState("");

  if (!showRejectForm) {
    return (
      <div className="flex gap-2">
        <button
          type="button"
          disabled={isSubmitting}
          onClick={onApprove}
          className="rounded-lg bg-accent-500 px-3 py-1 text-xs font-medium text-surface-950 hover:bg-accent-600 disabled:opacity-50"
        >
          核准
        </button>
        <button
          type="button"
          disabled={isSubmitting}
          onClick={() => setShowRejectForm(true)}
          className="rounded-lg border border-status-danger px-3 py-1 text-xs text-status-danger hover:bg-surface-800 disabled:opacity-50"
        >
          駁回
        </button>
      </div>
    );
  }

  return (
    <div className="space-y-2">
      <textarea
        value={note}
        onChange={(event) => setNote(event.target.value)}
        placeholder="請填寫駁回原因"
        rows={2}
        className="w-full min-w-[12rem] rounded-lg border border-border-subtle bg-surface-900 px-2 py-1 text-xs text-text-primary"
      />
      <div className="flex gap-2">
        <button
          type="button"
          disabled={!note.trim() || isSubmitting}
          onClick={() => onReject(note)}
          className="rounded-lg bg-status-danger px-3 py-1 text-xs font-medium text-surface-950 disabled:opacity-50"
        >
          確認駁回
        </button>
        <button
          type="button"
          onClick={() => {
            setShowRejectForm(false);
            setNote("");
          }}
          className="rounded-lg border border-border-subtle px-3 py-1 text-xs text-text-secondary"
        >
          取消
        </button>
      </div>
    </div>
  );
}
