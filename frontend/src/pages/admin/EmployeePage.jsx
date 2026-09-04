import { useEffect, useMemo, useRef, useState } from "react";
import { getDepartments } from "../../api/departments.api";
import {
  createUser,
  deleteUser,
  getAllPermissions,
  getUsers,
  setUserPermissions,
  updateUser,
} from "../../api/users.api";
import PermissionPanel from "../../components/PermissionPanel";
import { useAuth } from "../../context/AuthContext";
import { formatMonthDay } from "../../utils/datetime";
import { PERMISSION_BADGE_LABELS } from "../../utils/permissions";

const SELECTABLE_ROLES = ["manager", "employee"];
const ROLE_LABEL = { admin: "系統管理者", manager: "部門主管", employee: "一般員工" };

const inputClass =
  "rounded-lg border border-border-subtle bg-surface-900 px-2 py-1 text-sm text-text-primary focus:border-accent-500 focus:outline-none";

function DepartmentSelect({ value, onChange, departmentOptions, id }) {
  return (
    <select id={id} value={value} onChange={(event) => onChange(event.target.value)} className={inputClass}>
      <option value="">無</option>
      {departmentOptions.map((department) => (
        <option key={department.id} value={department.id}>
          {department.name}
        </option>
      ))}
    </select>
  );
}

function CreateUserForm({ departmentOptions, onCreated }) {
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [role, setRole] = useState(SELECTABLE_ROLES[1]);
  const [departmentId, setDepartmentId] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const isSubmittingRef = useRef(false);

  async function handleSubmit(event) {
    event.preventDefault();
    if (isSubmittingRef.current) return;
    isSubmittingRef.current = true;
    setIsSubmitting(true);
    setError("");
    try {
      const { user } = await createUser({
        name,
        email,
        role,
        department_id: departmentId ? Number(departmentId) : null,
        password,
      });
      onCreated(user);
      setName("");
      setEmail("");
      setRole(SELECTABLE_ROLES[1]);
      setDepartmentId("");
      setPassword("");
    } catch (err) {
      setError(err.response?.data?.error?.message ?? "建立失敗，請稍後再試。");
    } finally {
      isSubmittingRef.current = false;
      setIsSubmitting(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="glass-panel flex flex-wrap items-end gap-3 rounded-xl p-4">
      {error && <p className="w-full text-sm text-status-danger">{error}</p>}

      <div>
        <label htmlFor="new-user-name" className="mb-1 block text-xs text-text-muted">
          姓名
        </label>
        <input id="new-user-name" required value={name} onChange={(e) => setName(e.target.value)} className={inputClass} />
      </div>
      <div>
        <label htmlFor="new-user-email" className="mb-1 block text-xs text-text-muted">
          電子郵件
        </label>
        <input
          id="new-user-email" type="email" required value={email}
          onChange={(e) => setEmail(e.target.value)} className={inputClass}
        />
      </div>
      <div>
        <label htmlFor="new-user-role" className="mb-1 block text-xs text-text-muted">
          職位
        </label>
        <select id="new-user-role" value={role} onChange={(e) => setRole(e.target.value)} className={inputClass}>
          {SELECTABLE_ROLES.map((r) => (
            <option key={r} value={r}>
              {ROLE_LABEL[r]}
            </option>
          ))}
        </select>
      </div>
      <div>
        <label htmlFor="new-user-department" className="mb-1 block text-xs text-text-muted">
          部門
        </label>
        <DepartmentSelect
          id="new-user-department" value={departmentId} onChange={setDepartmentId} departmentOptions={departmentOptions}
        />
      </div>
      <div>
        <label htmlFor="new-user-password" className="mb-1 block text-xs text-text-muted">
          密碼
        </label>
        <input
          id="new-user-password" type="password" required value={password}
          onChange={(e) => setPassword(e.target.value)} className={inputClass}
        />
      </div>
      <button
        type="submit" disabled={isSubmitting}
        className="rounded-lg bg-accent-500 px-4 py-2 text-sm font-medium text-surface-950 hover:bg-accent-600 disabled:opacity-50"
      >
        {isSubmitting ? "建立中…" : "建立員工"}
      </button>
    </form>
  );
}

function PermissionCell({ permissions, onEdit, isEditing }) {
  return (
    <div className="space-y-1">
      {permissions.length === 0 && <span className="text-text-muted">—</span>}
      {permissions.map((p) => (
        <div key={p.permission}>
          <span className="rounded-full border border-accent-500 px-2 py-0.5 text-xs text-accent-400">
            {PERMISSION_BADGE_LABELS[p.permission] ?? p.permission}
          </span>
          <p className="text-xs text-text-muted">
            由 {p.granted_by_name ?? "已刪除的帳號"} 於 {formatMonthDay(p.granted_at)} 授予
          </p>
        </div>
      ))}
      {isEditing && (
        <button type="button" onClick={onEdit} className="text-xs text-accent-400 hover:underline">
          權限
        </button>
      )}
    </div>
  );
}

function EmployeeRow({ user, isAdmin, departmentOptions, permissions, onSaved, onDeleted }) {
  const [isEditing, setIsEditing] = useState(false);
  const [name, setName] = useState(user.name);
  const [email, setEmail] = useState(user.email);
  const [role, setRole] = useState(user.role);
  const [departmentId, setDepartmentId] = useState(user.department_id ?? "");
  const [extensionNumber, setExtensionNumber] = useState(user.extension_number ?? "");
  const [hireDate, setHireDate] = useState(user.hire_date ?? "");
  const [pendingPermissions, setPendingPermissions] = useState(permissions.map((p) => p.permission));
  const [showPermissionPanel, setShowPermissionPanel] = useState(false);
  const [confirmingDelete, setConfirmingDelete] = useState(false);
  const [error, setError] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);

  function startEdit() {
    setName(user.name);
    setEmail(user.email);
    setRole(user.role);
    setDepartmentId(user.department_id ?? "");
    setExtensionNumber(user.extension_number ?? "");
    setHireDate(user.hire_date ?? "");
    setPendingPermissions(permissions.map((p) => p.permission));
    setError("");
    setIsEditing(true);
  }

  async function handleSave() {
    setIsSubmitting(true);
    setError("");
    try {
      const { user: updatedUser } = await updateUser(user.id, {
        name,
        email,
        role,
        department_id: departmentId ? Number(departmentId) : null,
        extension_number: extensionNumber,
        hire_date: hireDate,
      });

      const originalKeys = permissions.map((p) => p.permission).sort().join(",");
      const nextKeys = [...pendingPermissions].sort().join(",");
      let updatedPermissions = null;
      if (isAdmin && originalKeys !== nextKeys) {
        const { permissions: rows } = await setUserPermissions(user.id, pendingPermissions);
        updatedPermissions = rows;
      }

      onSaved(updatedUser, updatedPermissions);
      setIsEditing(false);
    } catch (err) {
      setError(err.response?.data?.error?.message ?? "更新失敗，請稍後再試。");
    } finally {
      setIsSubmitting(false);
    }
  }

  async function handleDelete() {
    setIsSubmitting(true);
    setError("");
    try {
      await deleteUser(user.id);
      onDeleted(user.id);
    } catch (err) {
      setError(err.response?.data?.error?.message ?? "刪除失敗，請稍後再試。");
      setIsSubmitting(false);
    }
  }

  const canManage = isAdmin && user.role !== "admin";

  if (isEditing) {
    return (
      <tr className="border-b border-border-subtle last:border-0">
        <td className="px-4 py-3 text-text-muted">{user.employee_no}</td>
        <td className="px-4 py-3">
          <input value={name} onChange={(e) => setName(e.target.value)} className={inputClass} />
        </td>
        <td className="px-4 py-3">
          <input value={email} onChange={(e) => setEmail(e.target.value)} className={inputClass} />
        </td>
        <td className="px-4 py-3">
          <select value={role} onChange={(e) => setRole(e.target.value)} className={inputClass}>
            {SELECTABLE_ROLES.map((r) => (
              <option key={r} value={r}>
                {ROLE_LABEL[r]}
              </option>
            ))}
          </select>
        </td>
        <td className="px-4 py-3">
          <DepartmentSelect value={departmentId} onChange={setDepartmentId} departmentOptions={departmentOptions} />
        </td>
        <td className="px-4 py-3">
          <input value={extensionNumber} onChange={(e) => setExtensionNumber(e.target.value)} className={inputClass} />
        </td>
        <td className="px-4 py-3">
          <input type="date" value={hireDate} onChange={(e) => setHireDate(e.target.value)} className={inputClass} />
        </td>
        {isAdmin && (
          <td className="px-4 py-3">
            <PermissionCell permissions={permissions} isEditing onEdit={() => setShowPermissionPanel(true)} />
          </td>
        )}
        <td className="px-4 py-3">
          {error && <p className="mb-1 text-xs text-status-danger">{error}</p>}
          <div className="flex gap-2">
            <button
              type="button" disabled={isSubmitting} onClick={handleSave}
              className="rounded-lg bg-accent-500 px-3 py-1 text-xs font-medium text-surface-950 disabled:opacity-50"
            >
              儲存
            </button>
            <button
              type="button" onClick={() => setIsEditing(false)}
              className="rounded-lg border border-border-subtle px-3 py-1 text-xs text-text-secondary"
            >
              取消
            </button>
          </div>
          {showPermissionPanel && (
            <PermissionPanel
              selected={pendingPermissions}
              onChange={setPendingPermissions}
              onClose={() => setShowPermissionPanel(false)}
            />
          )}
        </td>
      </tr>
    );
  }

  return (
    <tr className="border-b border-border-subtle last:border-0">
      <td className="px-4 py-3 text-text-muted">{user.employee_no}</td>
      <td className="px-4 py-3 text-text-primary">{user.name}</td>
      <td className="px-4 py-3 text-text-primary">{user.email}</td>
      <td className="px-4 py-3 text-text-primary">{ROLE_LABEL[user.role]}</td>
      <td className="px-4 py-3 text-text-primary">{user.department_name ?? "—"}</td>
      <td className="px-4 py-3 text-text-primary">{user.extension_number ?? "—"}</td>
      <td className="px-4 py-3 text-text-primary">{user.hire_date}</td>
      {isAdmin && (
        <td className="px-4 py-3">
          <PermissionCell permissions={permissions} isEditing={false} onEdit={() => {}} />
        </td>
      )}
      {isAdmin && (
        <td className="px-4 py-3">
          {!canManage ? (
            <span className="text-xs text-text-muted">系統管理者帳號不提供編輯入口</span>
          ) : (
            <div className="flex flex-wrap gap-2">
              <button type="button" onClick={startEdit} className="text-xs text-accent-400 hover:underline">
                編輯
              </button>
              {confirmingDelete ? (
                <>
                  <button
                    type="button" disabled={isSubmitting} onClick={handleDelete}
                    className="text-xs text-status-danger hover:underline disabled:opacity-50"
                  >
                    確定刪除？
                  </button>
                  <button type="button" onClick={() => setConfirmingDelete(false)} className="text-xs text-text-secondary hover:underline">
                    取消
                  </button>
                </>
              ) : (
                <button type="button" onClick={() => setConfirmingDelete(true)} className="text-xs text-status-danger hover:underline">
                  刪除
                </button>
              )}
              {error && <p className="w-full text-xs text-status-danger">{error}</p>}
            </div>
          )}
        </td>
      )}
    </tr>
  );
}

function groupPermissionsByUser(rows) {
  const grouped = {};
  for (const row of rows) {
    if (!grouped[row.user_id]) grouped[row.user_id] = [];
    grouped[row.user_id].push(row);
  }
  return grouped;
}

export default function EmployeePage() {
  const { user: currentUser } = useAuth();
  const isAdmin = currentUser.role === "admin";
  const canViewDepartments = isAdmin || currentUser.role === "manager";

  const [users, setUsers] = useState([]);
  const [departments, setDepartments] = useState(null);
  const [permissionsByUser, setPermissionsByUser] = useState({});
  const [isLoading, setIsLoading] = useState(true);
  const [loadError, setLoadError] = useState("");

  useEffect(() => {
    let cancelled = false;

    async function load() {
      const [usersResult, departmentsResult, permissionsResult] = await Promise.allSettled([
        getUsers(),
        canViewDepartments ? getDepartments() : Promise.resolve(null),
        isAdmin ? getAllPermissions() : Promise.resolve(null),
      ]);
      if (cancelled) return;

      if (usersResult.status === "fulfilled") {
        setUsers(usersResult.value.users);
      } else {
        setLoadError("員工清單載入失敗，請重新整理。");
      }
      if (departmentsResult.status === "fulfilled" && departmentsResult.value) {
        setDepartments(departmentsResult.value.departments);
      }
      if (permissionsResult.status === "fulfilled" && permissionsResult.value) {
        setPermissionsByUser(groupPermissionsByUser(permissionsResult.value.permissions));
      }
      setIsLoading(false);
    }

    load();
    return () => {
      cancelled = true;
    };
  }, [isAdmin, canViewDepartments]);

  // employee 因 GET /departments 回 403，改從已載入的員工清單推導部門選項——
  // 不為了輔助篩選放寬 API 權限（見 docs/PITFALLS.md D1）。
  const departmentOptions = useMemo(() => {
    if (departments) {
      return departments.map((d) => ({ id: d.id, name: d.name }));
    }
    const seen = new Map();
    for (const u of users) {
      if (u.department_id != null && !seen.has(u.department_id)) {
        seen.set(u.department_id, u.department_name);
      }
    }
    return Array.from(seen, ([id, name]) => ({ id, name }));
  }, [departments, users]);

  function handleCreated(newUser) {
    setUsers((prev) => [...prev, newUser]);
  }

  function handleSaved(updatedUser, updatedPermissionRows) {
    setUsers((prev) => prev.map((u) => (u.id === updatedUser.id ? updatedUser : u)));
    if (updatedPermissionRows) {
      setPermissionsByUser((prev) => ({ ...prev, [updatedUser.id]: updatedPermissionRows }));
    }
  }

  function handleDeleted(userId) {
    setUsers((prev) => prev.filter((u) => u.id !== userId));
  }

  if (isLoading) {
    return <p className="text-sm text-text-muted">載入中…</p>;
  }

  if (loadError) {
    return <p className="text-sm text-status-danger">{loadError}</p>;
  }

  return (
    <div className="space-y-4">
      <h2 className="text-xl font-medium text-text-primary">員工資訊</h2>

      {isAdmin && <CreateUserForm departmentOptions={departmentOptions} onCreated={handleCreated} />}

      <div className="glass-panel overflow-x-auto rounded-xl">
        <table className="w-full text-left text-sm">
          <thead>
            <tr className="border-b border-border-subtle text-text-muted">
              <th className="px-4 py-3">員工編號</th>
              <th className="px-4 py-3">姓名</th>
              <th className="px-4 py-3">電子郵件</th>
              <th className="px-4 py-3">職位</th>
              <th className="px-4 py-3">部門</th>
              <th className="px-4 py-3">分機</th>
              <th className="px-4 py-3">到職日</th>
              {isAdmin && <th className="px-4 py-3">額外權限</th>}
              {isAdmin && <th className="px-4 py-3">操作</th>}
            </tr>
          </thead>
          <tbody>
            {users.map((user) => (
              <EmployeeRow
                key={user.id}
                user={user}
                isAdmin={isAdmin}
                departmentOptions={departmentOptions}
                permissions={permissionsByUser[user.id] ?? []}
                onSaved={handleSaved}
                onDeleted={handleDeleted}
              />
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
