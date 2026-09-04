import { useEffect, useRef, useState } from "react";
import { createDepartment, deleteDepartment, getDepartments, updateDepartment } from "../../api/departments.api";
import { getUsers } from "../../api/users.api";
import RoleGate from "../../components/RoleGate";

const inputClass =
  "rounded-lg border border-border-subtle bg-surface-900 px-2 py-1 text-sm text-text-primary focus:border-accent-500 focus:outline-none";

function eligibleManagers(users) {
  return users.filter((u) => u.role === "manager" || u.role === "admin");
}

function ManagerSelect({ value, onChange, managers, id }) {
  return (
    <select id={id} value={value} onChange={(event) => onChange(event.target.value)} className={inputClass}>
      <option value="">無</option>
      {managers.map((manager) => (
        <option key={manager.id} value={manager.id}>
          {manager.name}
        </option>
      ))}
    </select>
  );
}

function CreateDepartmentForm({ managers, onCreated }) {
  const [name, setName] = useState("");
  const [managerId, setManagerId] = useState("");
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
      const { department } = await createDepartment({ name, manager_id: managerId ? Number(managerId) : null });
      onCreated(department);
      setName("");
      setManagerId("");
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
        <label htmlFor="new-department-name" className="mb-1 block text-xs text-text-muted">
          部門名稱
        </label>
        <input
          id="new-department-name" required value={name} onChange={(e) => setName(e.target.value)} className={inputClass}
        />
      </div>
      <div>
        <label htmlFor="new-department-manager" className="mb-1 block text-xs text-text-muted">
          主管
        </label>
        <ManagerSelect id="new-department-manager" value={managerId} onChange={setManagerId} managers={managers} />
      </div>
      <button
        type="submit" disabled={isSubmitting}
        className="rounded-lg bg-accent-500 px-4 py-2 text-sm font-medium text-surface-950 hover:bg-accent-600 disabled:opacity-50"
      >
        {isSubmitting ? "建立中…" : "建立部門"}
      </button>
    </form>
  );
}

function DepartmentRow({ department, managers, onSaved, onDeleted }) {
  const [isEditing, setIsEditing] = useState(false);
  const [name, setName] = useState(department.name);
  const [managerId, setManagerId] = useState(department.manager_id ?? "");
  const [confirmingDelete, setConfirmingDelete] = useState(false);
  const [error, setError] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);

  function startEdit() {
    setName(department.name);
    setManagerId(department.manager_id ?? "");
    setError("");
    setIsEditing(true);
  }

  async function handleSave() {
    setIsSubmitting(true);
    setError("");
    try {
      const { department: updated } = await updateDepartment(department.id, {
        name,
        manager_id: managerId ? Number(managerId) : null,
      });
      onSaved(updated);
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
      await deleteDepartment(department.id);
      onDeleted(department.id);
    } catch (err) {
      setError(err.response?.data?.error?.message ?? "刪除失敗，請稍後再試。");
      setIsSubmitting(false);
    }
  }

  if (isEditing) {
    return (
      <tr className="border-b border-border-subtle last:border-0">
        <td className="px-4 py-3">
          <input value={name} onChange={(e) => setName(e.target.value)} className={inputClass} />
        </td>
        <td className="px-4 py-3">
          <ManagerSelect value={managerId} onChange={setManagerId} managers={managers} />
        </td>
        <td className="px-4 py-3 text-text-muted">{department.member_count}</td>
        <td className="px-4 py-3">
          {error && <p className="mb-1 text-xs text-status-danger">{error}</p>}
          <div className="flex gap-2">
            <button
              type="button" disabled={isSubmitting} onClick={handleSave}
              className="rounded-lg bg-accent-500 px-3 py-1 text-xs font-medium text-surface-950 disabled:opacity-50"
            >
              儲存
            </button>
            <button type="button" onClick={() => setIsEditing(false)} className="rounded-lg border border-border-subtle px-3 py-1 text-xs text-text-secondary">
              取消
            </button>
          </div>
        </td>
      </tr>
    );
  }

  return (
    <tr className="border-b border-border-subtle last:border-0">
      <td className="px-4 py-3 text-text-primary">{department.name}</td>
      <td className="px-4 py-3 text-text-primary">{department.manager_name ?? "—"}</td>
      <td className="px-4 py-3 text-text-primary">{department.member_count}</td>
      <td className="px-4 py-3">
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
      </td>
    </tr>
  );
}

function DepartmentContent() {
  const [departments, setDepartments] = useState([]);
  const [users, setUsers] = useState([]);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    Promise.all([getDepartments(), getUsers()]).then(([departmentsData, usersData]) => {
      setDepartments(departmentsData.departments);
      setUsers(usersData.users);
      setIsLoading(false);
    });
  }, []);

  const managers = eligibleManagers(users);

  function handleCreated(department) {
    setDepartments((prev) => [...prev, department]);
  }
  function handleSaved(updated) {
    setDepartments((prev) => prev.map((d) => (d.id === updated.id ? updated : d)));
  }
  function handleDeleted(departmentId) {
    setDepartments((prev) => prev.filter((d) => d.id !== departmentId));
  }

  if (isLoading) {
    return <p className="text-sm text-text-muted">載入中…</p>;
  }

  return (
    <div className="space-y-4">
      <h2 className="text-xl font-medium text-text-primary">部門管理</h2>

      <CreateDepartmentForm managers={managers} onCreated={handleCreated} />

      <div className="glass-panel overflow-x-auto rounded-xl">
        <table className="w-full text-left text-sm">
          <thead>
            <tr className="border-b border-border-subtle text-text-muted">
              <th className="px-4 py-3">名稱</th>
              <th className="px-4 py-3">主管</th>
              <th className="px-4 py-3">成員人數</th>
              <th className="px-4 py-3">操作</th>
            </tr>
          </thead>
          <tbody>
            {departments.map((department) => (
              <DepartmentRow
                key={department.id} department={department} managers={managers}
                onSaved={handleSaved} onDeleted={handleDeleted}
              />
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export default function DepartmentPage() {
  return (
    <RoleGate roles={["admin"]}>
      <DepartmentContent />
    </RoleGate>
  );
}
