import { formatTime } from "../utils/datetime";

// 下班打卡時間超過「正常工時結束時間 + 1 小時」時彈出（見 PunchPanel.jsx 的
// isLatePunchOut()）。下班打卡本身已經先完成（出勤紀錄已反映真實下班時間），
// 這個彈窗純粹是事後詢問「這段時間要不要順便去申請加班」，沒有「取消，先不
// 打卡」的選項——打卡已成事實，沒有可取消的動作。
//
// 門檻與文案不寫死「晚上 19:00」——那與正常工時結束時間無關（08:50 上班
// 18:50 下班已加班 30 分鐘卻不會跳出提示，19:05 下班卻一律跳出，兩者不一致）。
// 改為帶入當天實際的正常工時結束時間。選擇「算作處理私人事務」會呼叫 API
// 把固定文字寫入當日備註，供人資列印出勤紀錄查核。
//
// canApplyOvertime 為 false 時（距離加班起算點的可加班時間 < 30 分鐘）不顯示
// 「申請加班」選項——顯示了使用者也只會在下一步被後端 OVERTIME_TOO_SHORT 擋下。
export default function PunchOutConfirmDialog({
  normalWorkEnd,
  onMarkPersonalBusiness,
  isMarkingNote = false,
  onApplyOvertime,
  canApplyOvertime = true,
}) {
  const normalEndText = normalWorkEnd ? formatTime(normalWorkEnd) : null;
  const overdueText = normalEndText
    ? `已超過原本預計下班時間（${normalEndText}）一小時以上`
    : "已超過原本預計下班時間一小時以上";

  return (
    <div className="fixed inset-0 z-50 flex items-stretch justify-center bg-black/60 sm:items-center sm:p-4">
      <div className="glass-panel h-full w-full space-y-4 overflow-y-auto rounded-none p-6 sm:h-auto sm:max-w-sm sm:rounded-xl">
        <h3 className="text-lg font-medium text-text-primary">下班時間較晚</h3>
        <p className="text-sm text-text-secondary">
          {canApplyOvertime
            ? `下班打卡已完成，${overdueText}。這段時間是要算作處理私人事務，還是要申請加班？選擇處理私人事務會記錄在當天的出勤備註，供人資查核。`
            : `下班打卡已完成，${overdueText}，但可加班認列的時間不足 30 分鐘，這段時間僅能算作私人事務（會記錄在當天的出勤備註）。`}
        </p>

        <div className="flex flex-col gap-2">
          <button
            type="button"
            onClick={onMarkPersonalBusiness}
            disabled={isMarkingNote}
            className="rounded-lg border border-border-subtle px-4 py-2 text-sm text-text-secondary hover:border-accent-500 hover:text-text-primary disabled:opacity-50"
          >
            {isMarkingNote ? "記錄中…" : "算作處理私人事務"}
          </button>
          {canApplyOvertime && (
            <button
              type="button"
              onClick={onApplyOvertime}
              className="rounded-lg bg-accent-500 px-4 py-2 text-sm font-medium text-surface-950 hover:bg-accent-600"
            >
              前往申請加班
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
