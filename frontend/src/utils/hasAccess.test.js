import { describe, expect, test } from "vitest";
import { hasAccess } from "./hasAccess";

describe("hasAccess", () => {
  test("沒有使用者一律回傳 false", () => {
    expect(hasAccess(null, { roles: ["admin"] })).toBe(false);
  });

  test("角色命中即放行", () => {
    const user = { role: "manager", permissions: [] };
    expect(hasAccess(user, { roles: ["admin", "manager"] })).toBe(true);
  });

  test("角色不符但持有權限仍放行（OR 語意）", () => {
    const user = { role: "employee", permissions: ["exports.run"] };
    expect(hasAccess(user, { roles: ["admin"], permissions: ["exports.run"] })).toBe(true);
  });

  test("角色與權限皆不符時回傳 false", () => {
    const user = { role: "employee", permissions: ["holidays.manage"] };
    expect(hasAccess(user, { roles: ["admin"], permissions: ["exports.run"] })).toBe(false);
  });

  test("user.permissions 不存在時降級為無權限，不得崩潰", () => {
    const user = { role: "employee" };
    expect(hasAccess(user, { permissions: ["exports.run"] })).toBe(false);
  });

  test("未傳 roles／permissions 時只要有 user 就已經算沒有任何條件符合", () => {
    const user = { role: "employee", permissions: [] };
    expect(hasAccess(user)).toBe(false);
  });
});
