import { NavLink, Outlet } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import { hasAccess } from "../utils/hasAccess";

const ROLE_LABEL = {
  admin: "系統管理者",
  manager: "部門主管",
  employee: "一般員工",
};

// 選單只列**已經實作的路由**，後續批次各自把自己的頁面加進來。
// 可見性一律走 hasAccess()（與 RoleGate 共用同一份判定），不要在這裡另外
// 維護一份角色清單——那正是舊版「權限散落三處」的起點。
export const NAV_ITEMS = [
  { to: "/dashboard", label: "首頁", roles: ["admin", "manager", "employee"] },
  { to: "/attendance", label: "出勤紀錄", roles: ["admin", "manager", "employee"] },
];

export default function AppShell() {
  const { user, logout } = useAuth();
  const visibleNavItems = NAV_ITEMS.filter((item) =>
    hasAccess(user, { roles: item.roles, permissions: item.permissions }),
  );

  return (
    <div className="flex min-h-screen">
      <aside className="w-56 shrink-0 border-r border-border-subtle bg-surface-900 p-4">
        <p className="mb-6 text-lg font-medium text-accent-400">Employee Portal</p>
        <nav className="space-y-1">
          {visibleNavItems.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              className={({ isActive }) =>
                `block rounded-lg px-3 py-2 text-sm ${
                  isActive
                    ? "bg-surface-700 text-accent-400"
                    : "text-text-secondary hover:bg-surface-800 hover:text-text-primary"
                }`
              }
            >
              {item.label}
            </NavLink>
          ))}
        </nav>
      </aside>

      <div className="flex flex-1 flex-col">
        <header className="flex items-center justify-end gap-3 border-b border-border-subtle bg-surface-900 px-6 py-3">
          <span className="text-sm text-text-primary">{user.name}</span>
          <span className="rounded-full border border-accent-500 px-2 py-0.5 text-xs text-accent-400">
            {ROLE_LABEL[user.role]}
          </span>
          <button
            type="button"
            onClick={logout}
            className="text-sm text-text-secondary hover:text-status-danger"
          >
            登出
          </button>
        </header>

        <main className="flex-1 p-6">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
