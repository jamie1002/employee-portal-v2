// 可下放的細粒度權限白名單，須與後端 app/utils/constants.py 的 PERMISSION_KEYS
// 保持一致（見 SPEC.md §3.4）。
export const PERMISSION_KEYS = ["holidays.manage", "settings.manage", "exports.run"];

// 授權面板勾選項目用完整名稱；徽章空間有限，用簡短名稱。
export const PERMISSION_LABELS = {
  "holidays.manage": "國定假日管理",
  "settings.manage": "考勤設定",
  "exports.run": "匯出報表",
};

export const PERMISSION_BADGE_LABELS = {
  "holidays.manage": "國定假日",
  "settings.manage": "考勤設定",
  "exports.run": "匯出報表",
};
