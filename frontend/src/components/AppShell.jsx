import { useState } from "react";
import { NavLink, Outlet } from "react-router-dom";
import DemoClockControl from "./DemoClockControl";
import DemoResetButton from "./DemoResetButton";
import RoleGate from "./RoleGate";
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
  { to: "/leave-balance", label: "假別", roles: ["admin", "manager", "employee"] },
  { to: "/requests", label: "我的申請", roles: ["admin", "manager", "employee"] },
  { to: "/approvals", label: "審核中心", roles: ["admin", "manager"] },
  { to: "/venue", label: "場地借用", roles: ["admin", "manager", "employee"] },
  { to: "/chat", label: "AI 助理", roles: ["admin", "manager", "employee"] },
  { to: "/employees", label: "員工資訊", roles: ["admin", "manager", "employee"] },
  { to: "/departments", label: "部門管理", roles: ["admin"] },
  { to: "/holidays", label: "國定假日", roles: ["admin"], permissions: ["holidays.manage"] },
  { to: "/admin/attendance", label: "全公司出勤", roles: ["admin"] },
  { to: "/settings", label: "考勤設定", roles: ["admin"], permissions: ["settings.manage"] },
  { to: "/schema", label: "資料庫管理", roles: ["admin"] },
  { to: "/exports", label: "匯出報表", roles: ["admin", "manager"], permissions: ["exports.run"] },
];

export default function AppShell() {
  const { user, logout } = useAuth();
  const [isDrawerOpen, setIsDrawerOpen] = useState(false);
  const visibleNavItems = NAV_ITEMS.filter((item) =>
    hasAccess(user, { roles: item.roles, permissions: item.permissions }),
  );

  function closeDrawer() {
    setIsDrawerOpen(false);
  }

  return (
    <div className="flex min-h-screen">
      {/* 手機遮罩：只在抽屜開啟時才存在於 DOM，桌機（lg:）恆常不出現。 */}
      {isDrawerOpen && (
        <div
          data-testid="drawer-backdrop"
          onClick={closeDrawer}
          className="fixed inset-0 z-30 bg-black/60 lg:hidden"
        />
      )}

      {/* 側邊欄可見性一律用 CSS 控制（-translate-x-full / translate-x-0），
          不靠 JS 判斷視窗寬度——lg:translate-x-0 是無條件 class，桌機恆常可見、
          不受 isDrawerOpen 影響，抽屜開關只在手機斷點下才有視覺效果。 */}
      <aside
        data-testid="app-sidebar"
        data-state={isDrawerOpen ? "open" : "closed"}
        className={`fixed inset-y-0 left-0 z-40 w-56 shrink-0 border-r border-border-subtle bg-surface-900 p-4 transition-transform lg:static lg:translate-x-0 ${
          isDrawerOpen ? "translate-x-0" : "-translate-x-full"
        }`}
      >
        <p className="mb-6 text-lg font-medium text-accent-400">Employee Portal</p>
        <nav className="space-y-1">
          {visibleNavItems.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              onClick={closeDrawer}
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

      {/* min-w-0：flex item 預設 min-width:auto 會被內部（例如場地借用時間軸）
          min-w-[720px] 撐開，導致手機寬度下整頁出現水平捲軸——加這個才能讓
          overflow-x-auto 的內部捲動容器真正生效。 */}
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex flex-wrap items-center justify-between gap-3 border-b border-border-subtle bg-surface-900 px-4 py-3 sm:px-6">
          <div className="flex items-center gap-3">
            <button
              type="button"
              aria-label="開啟選單"
              onClick={() => setIsDrawerOpen(true)}
              className="flex h-11 w-11 items-center justify-center rounded-lg text-text-secondary hover:bg-surface-800 hover:text-text-primary lg:hidden"
            >
              <span aria-hidden="true" className="text-xl leading-none">
                ☰
              </span>
            </button>
            <DemoClockControl />
          </div>

          <div className="flex flex-wrap items-center gap-3">
            <RoleGate roles={["admin"]}>
              <DemoResetButton />
            </RoleGate>
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
          </div>
        </header>

        <main className="flex-1 p-4 sm:p-6">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
