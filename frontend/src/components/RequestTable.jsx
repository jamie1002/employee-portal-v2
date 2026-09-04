// 通用申請清單表格：columns 為 [{ key, label, render? }]，render(record) 缺省時直接顯示 record[key]。
// 手機／桌機同時渲染卡片與表格兩套結構（見 docs/UI-SPEC.md §2.4），靠 lg:hidden／
// hidden lg:block 切換，不用 JS 判斷視窗寬度。
export default function RequestTable({ records, columns, emptyMessage = "尚無申請紀錄。" }) {
  if (!records || records.length === 0) {
    return <div className="glass-panel rounded-xl p-8 text-center text-text-secondary">{emptyMessage}</div>;
  }

  return (
    <div className="space-y-3">
      <div data-testid="request-cards" className="space-y-3 lg:hidden">
        {records.map((record) => (
          <div key={record.id} className="glass-panel space-y-3 rounded-xl p-4">
            {columns.map((column) => (
              <div key={column.key}>
                <dt className="text-xs text-text-muted">{column.label}</dt>
                <dd className="mt-0.5 text-sm text-text-primary">
                  {column.render ? column.render(record) : (record[column.key] ?? "—")}
                </dd>
              </div>
            ))}
          </div>
        ))}
      </div>

      <div className="hidden glass-panel overflow-x-auto rounded-xl lg:block">
        <table className="w-full text-left text-sm">
          <thead>
            <tr className="border-b border-border-subtle text-text-muted">
              {columns.map((column) => (
                <th key={column.key} className="px-4 py-3">
                  {column.label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {records.map((record) => (
              <tr key={record.id} className="border-b border-border-subtle last:border-0">
                {columns.map((column) => (
                  <td key={column.key} className="px-4 py-3 text-text-primary">
                    {column.render ? column.render(record) : (record[column.key] ?? "—")}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
