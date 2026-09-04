"""跨模組共用的業務常數。"""

# 三組展示帳號固定不可變更密碼（見 SPEC.md §1）。
DEMO_ACCOUNT_EMAILS = frozenset({"admin@demo.com", "manager@demo.com", "employee@demo.com"})

# 可下放的細粒度權限白名單，與 db/migrations/001_baseline.sql 的
# user_permissions CHECK 約束保持一致（見 SPEC.md §3.4）。
PERMISSION_KEYS = frozenset({"holidays.manage", "settings.manage", "exports.run"})
