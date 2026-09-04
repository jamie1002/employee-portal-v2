// 通用申請清單表格：columns 為 [{ key, label, render? }]，render(record) 缺省時直接顯示 record[key]。
export default function RequestTable({ records, columns, emptyMessage = "尚無申請紀錄。" }) {
  if (!records || records.length === 0) {
    return <div className="glass-panel rounded-xl p-8 text-center text-text-secondary">{emptyMessage}</div>;
  }

  return (
    <div className="glass-panel overflow-x-auto rounded-xl">
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
  );
}
