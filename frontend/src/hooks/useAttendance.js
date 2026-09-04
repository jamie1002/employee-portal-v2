import { useEffect, useRef, useState } from "react";
import * as attendanceApi from "../api/attendance.api";

const DEFAULT_ERROR_MESSAGE = "操作失敗，請稍後再試。";

export function useAttendance() {
  const [today, setToday] = useState(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState(null);
  // useState 的更新不會在同一個事件迴圈內同步生效，快速連點可能在 disabled
  // 生效前重複送出，所以用 ref 做「檢查並設定」。
  const isSubmittingRef = useRef(false);

  async function refresh() {
    const { attendance } = await attendanceApi.getToday();
    setToday(attendance);
  }

  useEffect(() => {
    let cancelled = false;
    refresh()
      .catch(() => {
        if (!cancelled) setError(DEFAULT_ERROR_MESSAGE);
      })
      .finally(() => {
        if (!cancelled) setIsLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  // 打卡成功後直接以回應內容更新狀態卡；失敗（例如 409）時重新取得今日狀態，
  // 讓畫面與後端保持一致。回傳 attendance 供呼叫端判斷後續動作，失敗回 undefined。
  async function performPunch(action) {
    if (isSubmittingRef.current) return undefined;

    isSubmittingRef.current = true;
    setIsSubmitting(true);
    setError(null);
    try {
      const { attendance } = await action();
      setToday(attendance);
      return attendance;
    } catch (err) {
      setError(err.response?.data?.error?.message ?? DEFAULT_ERROR_MESSAGE);
      await refresh().catch(() => {});
      return undefined;
    } finally {
      isSubmittingRef.current = false;
      setIsSubmitting(false);
    }
  }

  return {
    today,
    isLoading,
    isSubmitting,
    error,
    punchIn: () => performPunch(attendanceApi.punchIn),
    punchOut: () => performPunch(attendanceApi.punchOut),
  };
}
