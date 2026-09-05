// 渲染面向使用者的使用手冊，而非開發向的 README.md（README 含技術決策與取捨紀錄，
// 對一般訪客是雜訊，見 README.md 開頭說明）。
import userGuideSource from "../../../docs/USER_GUIDE.md?raw";
import { SimpleMarkdown } from "./SimpleMarkdown";

export function AboutModal({ onClose }) {
  return (
    <div className="fixed inset-0 z-50 flex items-stretch justify-center bg-black/60 p-0 sm:items-center sm:p-4">
      <div className="glass-panel flex h-full w-full max-w-2xl flex-col rounded-none p-6 sm:h-auto sm:max-h-[85vh] sm:rounded-xl">
        <div className="flex items-center justify-between border-b border-border-subtle pb-3">
          <h3 className="text-lg font-semibold text-text-primary">專案說明</h3>
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg border border-border-subtle px-3 py-1 text-xs text-text-secondary hover:text-text-primary"
          >
            關閉
          </button>
        </div>
        <div className="mt-4 overflow-y-auto pr-2">
          <SimpleMarkdown source={userGuideSource} />
        </div>
      </div>
    </div>
  );
}
