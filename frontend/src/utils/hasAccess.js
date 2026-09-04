// 單一判定來源：AppShell 的選單過濾與 RoleGate 共用同一份邏輯，
// 不得各自維護一份角色清單（見 docs/UI-SPEC.md §4.2）。
export function hasAccess(user, { roles, permissions } = {}) {
  if (!user) return false;
  if (roles?.includes(user.role)) return true;
  return Boolean(permissions?.some((p) => (user.permissions ?? []).includes(p)));
}
