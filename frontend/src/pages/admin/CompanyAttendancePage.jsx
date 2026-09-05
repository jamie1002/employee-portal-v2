import { useEffect, useState } from "react";
import { getCompanyRecords } from "../../api/attendance.api";
import { getDepartments } from "../../api/departments.api";
import { getUsers } from "../../api/users.api";
import AttendanceTable from "../../components/AttendanceTable";
import DatePickerField from "../../components/DatePickerField";
import RoleGate from "../../components/RoleGate";
import { useVirtualToday } from "../../hooks/useVirtualClock";

// 狀態篩選比對的是生效值（見後端 attendance_effective.py），early_leave／
// missing_punch_out 是讀取時才衍生的判定，不是 status 欄位本身的列舉值。
const STATUS_OPTIONS = [
  { value: "", label: "全部狀態" },
  { value: "normal", label: "正常" },
  { value: "late", label: "遲到" },
  { value: "absent", label: "缺勤" },
  { value: "holiday_work", label: "假日出勤" },
  { value: "on_leave", label: "請假" },
  { value: "early_leave", label: "早退" },
  { value: "missing_punch_out", label: "未打下班卡" },
];

const inputClass =
  "w-full sm:w-auto rounded-lg border border-border-subtle bg-surface-900 px-3 py-2 text-sm text-text-primary focus:border-accent-500 focus:outline-none";

function CompanyAttendanceContent() {
  const [records, setRecords] = useState([]);
  const [departmentId, setDepartmentId] = useState("");
  const [userId, setUserId] = useState("");
  const [status, setStatus] = useState("");
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");
  const [users, setUsers] = useState([]);
  const [departments, setDepartments] = useState([]);
  const [isLoading, setIsLoading] = useState(true);
  // 欄位本身維持空白（不限日期、顯示全部），只有日曆彈出視窗的初始瀏覽月份
  // 用展示用虛擬時鐘的今天，不用真實現在時間（見 docs/PITFALLS.md B7）。
  const virtualToday = useVirtualToday();

  useEffect(() => {
    getUsers().then((data) => setUsers(data.users));
    getDepartments().then((data) => setDepartments(data.departments));
  }, []);

  // 選了部門就只列該部門員工，選「全公司」才列出全部人；切換部門時若已選
  // 員工不屬於新部門則清空，避免篩選條件互相矛盾（見 docs/UI-SPEC.md §3.14）。
  const employeeOptions = departmentId
    ? users.filter((u) => String(u.department_id) === String(departmentId))
    : users;

  function handleDepartmentChange(nextDepartmentId) {
    setDepartmentId(nextDepartmentId);
    const stillValid =
      !nextDepartmentId ||
      users.some((u) => String(u.id) === String(userId) && String(u.department_id) === String(nextDepartmentId));
    if (!stillValid) setUserId("");
  }

  useEffect(() => {
    let cancelled = false;
    setIsLoading(true);
    getCompanyRecords({
      department_id: departmentId || undefined,
      user_id: userId || undefined,
      status: status || undefined,
      start_date: startDate || undefined,
      end_date: endDate || undefined,
    })
      .then((data) => {
        if (!cancelled) setRecords(data.records);
      })
      .finally(() => {
        if (!cancelled) setIsLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [departmentId, userId, status, startDate, endDate]);

  return (
    <div className="space-y-4">
      <h2 className="text-xl font-medium text-text-primary">全公司出勤</h2>

      <div className="glass-panel flex flex-wrap items-end gap-4 rounded-xl p-4">
        <div className="w-full sm:w-auto">
          <label htmlFor="company-attendance-department" className="mb-1 block text-xs text-text-muted">
            部門
          </label>
          <select
            id="company-attendance-department"
            value={departmentId}
            onChange={(event) => handleDepartmentChange(event.target.value)}
            className={inputClass}
          >
            <option value="">全公司</option>
            {departments.map((department) => (
              <option key={department.id} value={department.id}>
                {department.name}
              </option>
            ))}
          </select>
        </div>
        <div className="w-full sm:w-auto">
          <label htmlFor="company-attendance-user" className="mb-1 block text-xs text-text-muted">
            使用者
          </label>
          <select
            id="company-attendance-user"
            value={userId}
            onChange={(event) => setUserId(event.target.value)}
            className={inputClass}
          >
            <option value="">全部使用者</option>
            {employeeOptions.map((user) => (
              <option key={user.id} value={user.id}>
                {user.name}
              </option>
            ))}
          </select>
        </div>
        <div className="w-full sm:w-auto">
          <label htmlFor="company-attendance-status" className="mb-1 block text-xs text-text-muted">
            狀態
          </label>
          <select
            id="company-attendance-status"
            value={status}
            onChange={(event) => setStatus(event.target.value)}
            className={inputClass}
          >
            {STATUS_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </div>
        <DatePickerField
          id="company-attendance-start-date"
          label="起始日期"
          value={startDate}
          initialViewDate={virtualToday}
          onChange={setStartDate}
          className="w-full sm:w-auto"
        />
        <DatePickerField
          id="company-attendance-end-date"
          label="結束日期"
          value={endDate}
          initialViewDate={virtualToday}
          onChange={setEndDate}
          className="w-full sm:w-auto"
        />
      </div>

      {isLoading ? (
        <div className="glass-panel rounded-xl p-8 text-center text-text-secondary">載入中…</div>
      ) : (
        <AttendanceTable
          records={records}
          showUser
          filters={{ user_id: userId || undefined, department_id: departmentId || undefined }}
        />
      )}
    </div>
  );
}

export default function CompanyAttendancePage() {
  return (
    <RoleGate roles={["admin"]}>
      <CompanyAttendanceContent />
    </RoleGate>
  );
}
