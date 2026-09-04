import { useEffect, useRef, useState } from "react";
import { getDemoClock } from "../api/demo.api";

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
