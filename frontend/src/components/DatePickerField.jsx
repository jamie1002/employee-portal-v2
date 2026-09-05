import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import {
  addMonths,
  eachDayOfInterval,
  endOfMonth,
  endOfWeek,
  format,
  isSameDay,
  isSameMonth,
  parseISO,
  startOfMonth,
  startOfWeek,
  subMonths,
} from "date-fns";

const WEEKDAY_LABELS = ["日", "一", "二", "三", "四", "五", "六"];
const POPOVER_WIDTH = 256; // w-64

function toDate(value) {
  return value ? parseISO(value) : null;
}

/**
 * 日期篩選欄位：值可以是空字串（代表「不限日期、顯示全部」）。
 *
 * 跟瀏覽器原生 `<input type="date">` 的差異——原生選擇器在欄位空白時，
 * 一律以瀏覽器的真實現在時間決定日曆初始顯示的月份；這個系統的「今天」
 * 固定鎖在展示視窗（2026-08-24 ~ 08-31），沒有任何辦法只靠 min/max 屬性
 * 保證原生選擇器的初始顯示月份，且會隨真實時間流逝持續跟展示視窗拉開
 * 距離（見 docs/PITFALLS.md B7）。這裡自己刻日曆 UI，欄位空白時一律以
 * `initialViewDate`（呼叫端傳入 useVirtualToday() 取得的展示今天）決定
 * 初始顯示月份，不受真實時間影響。
 *
 * 彈出面板用 createPortal 掛到 document.body，不直接巢狀在觸發按鈕底下：
 * 這個欄位常被放在 `.glass-panel` 篩選列裡，`.glass-panel` 的
 * `backdrop-filter` 會建立新的堆疊環境（stacking context），把面板的
 * z-index 關在那個環境裡面出不去，導致面板實際上被畫面下方後面的內容
 * （例如出勤紀錄清單）蓋住——DOM 與可及性樹都正常、視覺上卻完全看不到，
 * 排查花了不少時間才用 elementFromPoint 抓到真凶。掛到 body 之後完全跳脫
 * 這個問題，且不用擔心未來任何一層祖先加上 transform/filter/opacity 又
 * 重新踩到同一個坑。
 */
export default function DatePickerField({ id, label, value, onChange, initialViewDate, className = "" }) {
  const [isOpen, setIsOpen] = useState(false);
  const [viewMonth, setViewMonth] = useState(() => startOfMonth(toDate(value) ?? toDate(initialViewDate) ?? new Date()));
  const [position, setPosition] = useState(null);
  const triggerRef = useRef(null);
  const popoverRef = useRef(null);

  // 掛載當下 initialViewDate 常常還是 null（useVirtualToday() 非同步取得），
  // 等它真正 resolve、且欄位仍是空白時，把預設瀏覽月份補上。
  useEffect(() => {
    if (!value && initialViewDate) setViewMonth(startOfMonth(toDate(initialViewDate)));
  }, [initialViewDate, value]);

  useEffect(() => {
    if (!isOpen) return;

    function isOutside(target) {
      return !triggerRef.current?.contains(target) && !popoverRef.current?.contains(target);
    }
    function handleClickOutside(event) {
      if (isOutside(event.target)) setIsOpen(false);
    }
    function handleKeyDown(event) {
      if (event.key === "Escape") setIsOpen(false);
    }
    // 面板用 position: fixed 定位在觸發按鈕底下，只在開啟當下計算一次；
    // 頁面捲動或視窗尺寸改變都直接關閉，不追著重新定位——這是簡單篩選欄位，
    // 不值得為了「捲動時面板跟著走」增加複雜度。
    function handleClose() {
      setIsOpen(false);
    }
    document.addEventListener("mousedown", handleClickOutside);
    document.addEventListener("keydown", handleKeyDown);
    window.addEventListener("scroll", handleClose, true);
    window.addEventListener("resize", handleClose);
    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
      document.removeEventListener("keydown", handleKeyDown);
      window.removeEventListener("scroll", handleClose, true);
      window.removeEventListener("resize", handleClose);
    };
  }, [isOpen]);

  function openPicker() {
    setViewMonth(startOfMonth(toDate(value) ?? toDate(initialViewDate) ?? new Date()));
    const rect = triggerRef.current.getBoundingClientRect();
    const left = Math.min(rect.left, window.innerWidth - POPOVER_WIDTH - 8);
    setPosition({ top: rect.bottom + 4, left: Math.max(8, left) });
    setIsOpen(true);
  }

  function selectDay(day) {
    onChange(format(day, "yyyy-MM-dd"));
    setIsOpen(false);
  }

  const gridStart = startOfWeek(startOfMonth(viewMonth));
  const gridEnd = endOfWeek(endOfMonth(viewMonth));
  const days = eachDayOfInterval({ start: gridStart, end: gridEnd });
  const selectedDate = toDate(value);

  return (
    <div className={className}>
      {/* 刻意不用 htmlFor 把這段文字跟下面的 <button> 綁成 <label> 關聯——那會讓
          按鈕的無障礙名稱被這段固定文字蓋掉，永遠唸出「日期」而不是目前選到的
          日期或「不限日期」，等於把真正有意義的內容藏起來。純粹當視覺標題用。 */}
      {label && <span className="mb-1 block text-xs text-text-muted">{label}</span>}
      <button
        ref={triggerRef}
        id={id}
        type="button"
        onClick={() => (isOpen ? setIsOpen(false) : openPicker())}
        className="w-full sm:w-auto rounded-lg border border-border-subtle bg-surface-900 px-3 py-2 text-left text-sm text-text-primary focus:border-accent-500 focus:outline-none"
      >
        {value || <span className="text-text-muted">不限日期</span>}
      </button>

      {isOpen &&
        position &&
        createPortal(
          <div
            ref={popoverRef}
            style={{ top: position.top, left: position.left, width: POPOVER_WIDTH }}
            className="glass-panel fixed z-50 rounded-xl p-3 shadow-lg"
          >
            <div className="mb-2 flex items-center justify-between">
              <button
                type="button"
                onClick={() => setViewMonth((month) => subMonths(month, 1))}
                aria-label="上個月"
                className="rounded-lg px-2 py-1 text-text-secondary hover:bg-surface-800 hover:text-text-primary"
              >
                ‹
              </button>
              <span className="text-sm font-medium text-text-primary">{format(viewMonth, "yyyy 年 M 月")}</span>
              <button
                type="button"
                onClick={() => setViewMonth((month) => addMonths(month, 1))}
                aria-label="下個月"
                className="rounded-lg px-2 py-1 text-text-secondary hover:bg-surface-800 hover:text-text-primary"
              >
                ›
              </button>
            </div>

            <div className="grid grid-cols-7 gap-1 text-center text-xs text-text-muted">
              {WEEKDAY_LABELS.map((weekday) => (
                <div key={weekday} className="py-1">
                  {weekday}
                </div>
              ))}
            </div>

            <div className="grid grid-cols-7 gap-1">
              {days.map((day) => {
                const isSelected = selectedDate && isSameDay(day, selectedDate);
                const inCurrentMonth = isSameMonth(day, viewMonth);
                return (
                  <button
                    key={day.toISOString()}
                    type="button"
                    onClick={() => selectDay(day)}
                    className={[
                      "rounded-lg py-1 text-xs",
                      isSelected ? "bg-accent-500 text-surface-950" : "text-text-primary hover:bg-surface-800",
                      !inCurrentMonth && !isSelected ? "text-text-muted" : "",
                    ].join(" ")}
                  >
                    {format(day, "d")}
                  </button>
                );
              })}
            </div>

            {value && (
              <button
                type="button"
                onClick={() => {
                  onChange("");
                  setIsOpen(false);
                }}
                className="mt-2 w-full rounded-lg border border-border-subtle py-1 text-xs text-text-secondary hover:border-accent-500 hover:text-text-primary"
              >
                清除
              </button>
            )}
          </div>,
          document.body,
        )}
    </div>
  );
}
