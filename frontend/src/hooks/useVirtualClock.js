import { useEffect, useRef, useState } from "react";
import { getDemoClock } from "../api/demo.api";
import { taipeiDateKey } from "../utils/datetime";

const RESYNC_INTERVAL_MS = 60_000;
const TICK_INTERVAL_MS = 1_000;

// 顯示一律每秒本地推算、每 60 秒重新向後端校正，否則畫面時間是死的、
// 打卡是活的：後端的虛擬時鐘持續走動，只在掛載時取一次會讓兩者對不起來
// （見 docs/PITFALLS.md B3）。
export function useVirtualClock() {
  const [virtualNow, setVirtualNow] = useState(null);
  const offsetMsRef = useRef(0); // 後端虛擬時間 - 本機 Date.now() 的差值

  useEffect(() => {
    let cancelled = false;

    async function sync() {
      try {
        const { virtual_now } = await getDemoClock();
        if (cancelled) return;
        offsetMsRef.current = new Date(virtual_now).getTime() - Date.now();
        setVirtualNow(new Date(Date.now() + offsetMsRef.current));
      } catch {
        // 校正失敗就維持上次推算值，下一輪 60 秒後再試，不打斷本地走動。
      }
    }

    sync();
    const resyncId = setInterval(sync, RESYNC_INTERVAL_MS);
    const tickId = setInterval(() => {
      if (!cancelled) setVirtualNow(new Date(Date.now() + offsetMsRef.current));
    }, TICK_INTERVAL_MS);

    return () => {
      cancelled = true;
      clearInterval(resyncId);
      clearInterval(tickId);
    };
  }, []);

  return virtualNow;
}

// 日期選擇欄位的預設值一律用這個 hook，取展示用虛擬時鐘的「今天」（台北曆法日期）
// ——不要留空讓瀏覽器原生的日期選擇器用真實現在時間頂替（見 docs/PITFALLS.md B6）。
// 只取一次、不逐秒更新：日期預設值不需要秒級精度，沒必要多訂閱一個每秒 re-render
// 的來源。
export function useVirtualToday() {
  const [today, setToday] = useState(null);

  useEffect(() => {
    let cancelled = false;
    getDemoClock()
      .then(({ virtual_now }) => {
        if (!cancelled) setToday(taipeiDateKey(virtual_now));
      })
      .catch(() => {
        // 取不到就維持 null，呼叫端的欄位保持空白——留給使用者手動輸入，
        // 不要在這裡拋出讓整頁掛掉。
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return today; // "YYYY-MM-DD"，載入完成前為 null
}
