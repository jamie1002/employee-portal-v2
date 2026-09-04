import { useAuth } from "../context/AuthContext";
import { hasAccess } from "../utils/hasAccess";

// 兩者為 OR 語意，皆不符時回傳 null——完全不渲染，children 內部的資料載入
// effect 也不會觸發（見 docs/UI-SPEC.md §4.1）。
export default function RoleGate({ roles, permissions, children }) {
  const { user } = useAuth();

  if (!hasAccess(user, { roles, permissions })) {
    return null;
  }

  return children;
}
