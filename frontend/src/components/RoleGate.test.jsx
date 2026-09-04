import { render, screen } from "@testing-library/react";
import { vi } from "vitest";
import RoleGate from "./RoleGate";

const mockUseAuth = vi.fn();
vi.mock("../context/AuthContext", () => ({
  useAuth: () => mockUseAuth(),
}));

test("角色命中時渲染 children", () => {
  mockUseAuth.mockReturnValue({ user: { role: "admin", permissions: [] } });

  render(
    <RoleGate roles={["admin"]}>
      <div>秘密內容</div>
    </RoleGate>,
  );

  expect(screen.getByText("秘密內容")).toBeInTheDocument();
});

test("角色與權限皆不符時完全不渲染", () => {
  mockUseAuth.mockReturnValue({ user: { role: "employee", permissions: [] } });

  render(
    <RoleGate roles={["admin"]} permissions={["exports.run"]}>
      <div>秘密內容</div>
    </RoleGate>,
  );

  expect(screen.queryByText("秘密內容")).not.toBeInTheDocument();
});

test("持有對應權限時即使角色不符也放行", () => {
  mockUseAuth.mockReturnValue({ user: { role: "employee", permissions: ["exports.run"] } });

  render(
    <RoleGate roles={["admin", "manager"]} permissions={["exports.run"]}>
      <div>匯出報表入口</div>
    </RoleGate>,
  );

  expect(screen.getByText("匯出報表入口")).toBeInTheDocument();
});
