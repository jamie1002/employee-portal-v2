import { useEffect, useMemo, useState } from "react";
import { downloadExportXlsx, getExportPreview } from "../../api/export.api";
import { getDepartments } from "../../api/departments.api";
import { getUsers } from "../../api/users.api";
import RoleGate from "../../components/RoleGate";
import { useAuth } from "../../context/AuthContext";

const KIND_OPTIONS = [
  { value: "employees", label: "員工資料" },
  { value: "attendance", label: "出勤（生效值）" },
  { value: "attendance-raw", label: "出勤（原始打卡）" },
  { value: "attendance-changes", label: "出勤異動" },
  { value: "room-bookings", label: "場地預約" },
];

const ATTENDANCE_LIKE_KINDS = ["attendance", "attendance-raw", "attendance-changes"];

// 每個匯出類型允許的欄位，須與後端 app/schemas/export.py 的 EXPORT_COLUMNS 保持
// 一致——兩邊各自維護一份是刻意的，沒有共用 schema 的 API（同一份規格文件已足夠
// 兩邊對齊，見舊專案同樣的作法）。
const COLUMNS_BY_KIND = {
  employees: [
    ["employee_no", "員工編號"], ["name", "姓名"], ["email", "電子郵件"], ["role", "職位"],
    ["department_name", "部門"], ["extension_number", "分機"], ["hire_date", "到職日"],
  ],
  attendance: [
    ["employee_no", "員工編號"], ["user_name", "姓名"], ["department_name", "部門"], ["punch_date", "日期"],
    ["effective_punch_in_time", "上班時間"], ["effective_punch_out_time", "下班時間"],
    ["effective_status", "狀態"], ["effective_work_hours", "工時"], ["effective_is_early_leave", "早退"],
    ["is_missing_punch_out", "未打下班卡"], ["is_adjusted", "已異動"], ["note", "備註"],
  ],
  "attendance-raw": [
    ["employee_no", "員工編號"], ["user_name", "姓名"], ["department_name", "部門"], ["punch_date", "日期"],
    ["punch_in_time", "上班時間"], ["punch_out_time", "下班時間"], ["status", "狀態"],
    ["work_hours", "工時"], ["is_early_leave", "早退"], ["note", "備註"],
  ],
  "attendance-changes": [
    ["employee_no", "員工編號"], ["user_name", "姓名"], ["department_name", "部門"],
    ["request_type", "申請類型"], ["period", "期間"], ["detail", "內容"], ["status", "狀態"],
    ["submitted_at", "申請時間"], ["reviewer_name", "審核人"], ["reviewed_at", "審核時間"], ["review_note", "審核意見"],
  ],
  "room-bookings": [
    ["room_name", "場地"], ["booked_by_name", "預約人"], ["department_name", "部門"],
    ["title", "標題"], ["start_time", "開始時間"], ["end_time", "結束時間"], ["status", "狀態"],
  ],
};

const inputClass =
  "rounded-lg border border-border-subtle bg-surface-900 px-2 py-1 text-sm text-text-primary focus:border-accent-500 focus:outline-none";

// FileReader 而非 Blob.text()：兩者在真實瀏覽器都能用，但 FileReader 在測試
// 環境（jsdom）也有完整支援，Blob.text() 沒有——用它才能在 CI 裡跑得動這段。
function readBlobAsText(blob) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result);
    reader.onerror = () => reject(reader.error);
    reader.readAsText(blob);
  });
}

async function extractErrorMessage(err, fallback) {
  const data = err.response?.data;
  if (data instanceof Blob) {
    try {
      const parsed = JSON.parse(await readBlobAsText(data));
      return parsed?.error?.message ?? fallback;
    } catch {
      return fallback;
    }
  }
  return err.response?.data?.error?.message ?? fallback;
}

function downloadBlob(blob, filename) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}

function ExportContent() {
  const { user: currentUser } = useAuth();
  const isAdmin = currentUser.role === "admin";
  // 不是 admin 一律限縮（deny-by-default），不寫成「是 manager 才限縮」——
  // 被授予 exports.run 的一般員工也適用同一條規則（見 docs/PITFALLS.md C1）。
  const isRestricted = !isAdmin;

  const [kind, setKind] = useState(KIND_OPTIONS[0].value);
  const [selectedColumns, setSelectedColumns] = useState(COLUMNS_BY_KIND[KIND_OPTIONS[0].value].map(([key]) => key));
  const [departmentId, setDepartmentId] = useState("");
  const [userId, setUserId] = useState("");
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");
  const [departments, setDepartments] = useState([]);
  const [users, setUsers] = useState([]);
  const [preview, setPreview] = useState(null);
  const [isLoadingPreview, setIsLoadingPreview] = useState(false);
  const [isDownloading, setIsDownloading] = useState(false);
  const [error, setError] = useState("");

  const showDepartmentFilter = isAdmin || kind === "room-bookings";
  const showEmployeeFilter = ATTENDANCE_LIKE_KINDS.includes(kind);
  const showDateFilters = kind !== "employees";

  useEffect(() => {
    if (isAdmin) getDepartments().then(({ departments: rows }) => setDepartments(rows));
    getUsers().then(({ users: rows }) => setUsers(rows));
  }, [isAdmin]);

  const employeeOptions = useMemo(() => {
    if (isRestricted) {
      return users.filter((u) => u.department_id === currentUser.department_id);
    }
    if (departmentId) {
      return users.filter((u) => String(u.department_id) === String(departmentId));
    }
    return users;
  }, [users, isRestricted, departmentId, currentUser.department_id]);

  function handleKindChange(nextKind) {
    setKind(nextKind);
    setSelectedColumns(COLUMNS_BY_KIND[nextKind].map(([key]) => key));
    setDepartmentId("");
    setUserId("");
    setStartDate("");
    setEndDate("");
    setPreview(null);
    setError("");
  }

  function handleDepartmentChange(value) {
    setDepartmentId(value);
    if (userId) {
      const stillValid = users.some((u) => String(u.id) === userId && String(u.department_id) === value);
      if (!stillValid) setUserId("");
    }
  }

  function toggleColumn(key) {
    setSelectedColumns((prev) => (prev.includes(key) ? prev.filter((k) => k !== key) : [...prev, key]));
  }

  function buildFilters() {
    const filters = {};
    if (showDepartmentFilter && departmentId) filters.department_id = Number(departmentId);
    if (showEmployeeFilter && userId) filters.user_id = Number(userId);
    if (showDateFilters) {
      if (startDate) filters.start_date = startDate;
      if (endDate) filters.end_date = endDate;
    }
    return filters;
  }

  async function handlePreview() {
    setIsLoadingPreview(true);
    setError("");
    try {
      const data = await getExportPreview(kind, buildFilters(), selectedColumns);
      setPreview(data);
    } catch (err) {
      setError(err.response?.data?.error?.message ?? "預覽失敗，請稍後再試。");
    } finally {
      setIsLoadingPreview(false);
    }
  }

  async function handleDownload() {
    setIsDownloading(true);
    setError("");
    try {
      const blob = await downloadExportXlsx(kind, buildFilters(), selectedColumns);
      downloadBlob(blob, `${kind}.xlsx`);
    } catch (err) {
      setError(await extractErrorMessage(err, "下載失敗，請稍後再試。"));
    } finally {
      setIsDownloading(false);
    }
  }

  const noColumnsSelected = selectedColumns.length === 0;

  return (
    <div className="space-y-4">
      <h2 className="text-xl font-medium text-text-primary">匯出報表</h2>

      {error && <p className="text-sm text-status-danger">{error}</p>}

      <div className="glass-panel space-y-4 rounded-xl p-6">
        <div className="flex flex-wrap items-end gap-4">
          <div>
            <label htmlFor="export-kind" className="mb-1 block text-xs text-text-muted">
              資料類型
            </label>
            <select
              id="export-kind" value={kind} onChange={(e) => handleKindChange(e.target.value)} className={inputClass}
            >
              {KIND_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </div>

          {showDepartmentFilter && (
            <div>
              <label htmlFor="export-department" className="mb-1 block text-xs text-text-muted">
                部門
              </label>
              <select
                id="export-department" value={departmentId}
                onChange={(e) => handleDepartmentChange(e.target.value)} className={inputClass}
              >
                <option value="">全部</option>
                {departments.map((department) => (
                  <option key={department.id} value={department.id}>
                    {department.name}
                  </option>
                ))}
              </select>
            </div>
          )}

          {!showDepartmentFilter && (
            <p className="text-xs text-text-muted">僅能匯出所屬部門資料，範圍由後端強制限定。</p>
          )}

          {showEmployeeFilter && (
            <div>
              <label htmlFor="export-user" className="mb-1 block text-xs text-text-muted">
                員工
              </label>
              <select id="export-user" value={userId} onChange={(e) => setUserId(e.target.value)} className={inputClass}>
                <option value="">全部</option>
                {employeeOptions.map((employee) => (
                  <option key={employee.id} value={employee.id}>
                    {employee.name}
                  </option>
                ))}
              </select>
            </div>
          )}

          {showDateFilters && (
            <>
              <div>
                <label htmlFor="export-start-date" className="mb-1 block text-xs text-text-muted">
                  起始日期
                </label>
                <input
                  id="export-start-date" type="date" value={startDate}
                  onChange={(e) => setStartDate(e.target.value)} className={inputClass}
                />
              </div>
              <div>
                <label htmlFor="export-end-date" className="mb-1 block text-xs text-text-muted">
                  結束日期
                </label>
                <input
                  id="export-end-date" type="date" value={endDate}
                  onChange={(e) => setEndDate(e.target.value)} className={inputClass}
                />
              </div>
            </>
          )}
        </div>

        <div>
          <p className="mb-2 text-xs text-text-muted">欄位</p>
          <div className="flex flex-wrap gap-3">
            {COLUMNS_BY_KIND[kind].map(([key, label]) => (
              <label key={key} className="flex items-center gap-1 text-sm text-text-primary">
                <input type="checkbox" checked={selectedColumns.includes(key)} onChange={() => toggleColumn(key)} />
                {label}
              </label>
            ))}
          </div>
        </div>

        <div className="flex gap-2">
          <button
            type="button" disabled={noColumnsSelected || isLoadingPreview} onClick={handlePreview}
            className="rounded-lg border border-accent-500 px-4 py-2 text-sm text-accent-400 hover:bg-surface-800 disabled:opacity-50"
          >
            {isLoadingPreview ? "載入中…" : "預覽"}
          </button>
          <button
            type="button" disabled={noColumnsSelected || isDownloading} onClick={handleDownload}
            className="rounded-lg bg-accent-500 px-4 py-2 text-sm font-medium text-surface-950 hover:bg-accent-600 disabled:opacity-50"
          >
            {isDownloading ? "下載中…" : "下載 .xlsx"}
          </button>
        </div>
      </div>

      {preview && (
        <div className="glass-panel overflow-x-auto rounded-xl">
          <table className="w-full text-left text-sm">
            <thead>
              <tr className="border-b border-border-subtle text-text-muted">
                {preview.columns.map((column) => (
                  <th key={column.key} className="whitespace-nowrap px-4 py-3">
                    {column.label}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {preview.rows.map((row, index) => (
                <tr key={index} className="border-b border-border-subtle last:border-0">
                  {row.map((value, cellIndex) => (
                    <td key={cellIndex} className="whitespace-nowrap px-4 py-3 text-text-primary">
                      {value === null || value === undefined ? "—" : String(value)}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
          {preview.rows.length === 0 && <p className="p-4 text-sm text-text-muted">查無資料。</p>}
        </div>
      )}
    </div>
  );
}

export default function ExportPage() {
  return (
    <RoleGate roles={["admin", "manager"]} permissions={["exports.run"]}>
      <ExportContent />
    </RoleGate>
  );
}
