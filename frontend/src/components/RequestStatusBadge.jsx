const STATUS_LABEL = { pending: "待審", approved: "已核准", rejected: "已駁回" };
const STATUS_CLASS = {
  pending: "text-status-late border-status-late",
  approved: "text-status-normal border-status-normal",
  rejected: "text-status-danger border-status-danger",
};

export default function RequestStatusBadge({ status }) {
  return (
    <span className={`rounded-full border px-2 py-0.5 text-xs ${STATUS_CLASS[status] ?? ""}`}>
      {STATUS_LABEL[status] ?? status ?? "—"}
    </span>
  );
}
