import { PERMISSION_KEYS, PERMISSION_LABELS } from "../utils/permissions";

// 獨立面板（非 inline 下拉）：勾選狀態暫存在呼叫端，關閉面板不代表儲存——
// 實際送出權限 API 是呼叫端在按「儲存」時才做（見 docs/UI-SPEC.md §3.11）。
export default function PermissionPanel({ selected, onChange, onClose }) {
  function toggle(key) {
    onChange(selected.includes(key) ? selected.filter((p) => p !== key) : [...selected, key]);
  }

  return (
    <div className="fixed inset-0 z-50 flex items-stretch justify-center bg-black/60 sm:items-center sm:p-4">
      <div className="glass-panel h-full w-full space-y-4 overflow-y-auto rounded-none p-6 sm:h-auto sm:max-w-sm sm:rounded-xl">
        <h3 className="text-lg font-medium text-text-primary">額外權限</h3>

        <div className="space-y-2">
          {PERMISSION_KEYS.map((key) => (
            <label key={key} className="flex items-center gap-2 text-sm text-text-primary">
              <input type="checkbox" checked={selected.includes(key)} onChange={() => toggle(key)} />
              {PERMISSION_LABELS[key]}
            </label>
          ))}
        </div>

        <div className="flex justify-end">
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg bg-accent-500 px-4 py-2 text-sm font-medium text-surface-950 hover:bg-accent-600"
          >
            完成
          </button>
        </div>
      </div>
    </div>
  );
}
