import axios from "axios";

const TOKEN_STORAGE_KEY = "auth_token";
const SLOW_REQUEST_THRESHOLD_MS = 3000;

let requestSeq = 0;
const pendingTimers = new Map();
const slowRequestIds = new Set();
const listeners = new Set();

function notify() {
  for (const listener of listeners) listener();
}

// ColdStartBanner 透過 useSyncExternalStore 訂閱這個集合的變化。用集合而非
// 單一布林值，是因為兩個並行的慢請求中，先完成的那個不該把橫幅關掉——
// Render 免費方案冷啟動時，畫面掛載常會同時打好幾支 API。
export function subscribeSlowRequests(listener) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function getSlowRequestCount() {
  return slowRequestIds.size;
}

function clearRequest(requestId) {
  const timerId = pendingTimers.get(requestId);
  if (timerId !== undefined) {
    clearTimeout(timerId);
    pendingTimers.delete(requestId);
  }
  if (slowRequestIds.delete(requestId)) {
    notify();
  }
}

const apiClient = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL ?? "http://localhost:3000/api",
});

apiClient.interceptors.request.use((config) => {
  const token = localStorage.getItem(TOKEN_STORAGE_KEY);
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }

  const requestId = ++requestSeq;
  config.__requestId = requestId;

  // opt-in：AI 助理的回答本來就常超過這個門檻（生成本身要 1～3 秒，冷啟動時更久），
  // 硬套用這個計時器會顯示「伺服器喚醒中」橫幅，誤導成冷啟動、實際上是模型在生成。
  // 既有呼叫端都不帶這個旗標，行為不變。
  if (!config.skipSlowRequestTracking) {
    const timerId = setTimeout(() => {
      slowRequestIds.add(requestId);
      notify();
    }, SLOW_REQUEST_THRESHOLD_MS);
    pendingTimers.set(requestId, timerId);
  }

  return config;
});

// 401 一律代表 token 缺失／無效／逾期，清掉本機憑證；
// 由 AuthContext 依照自己的 user 狀態決定要不要導頁，這裡不做任何導頁動作。
apiClient.interceptors.response.use(
  (response) => {
    clearRequest(response.config.__requestId);
    return response;
  },
  (error) => {
    if (error.config) {
      clearRequest(error.config.__requestId);
    }
    if (error.response?.status === 401) {
      localStorage.removeItem(TOKEN_STORAGE_KEY);
    }
    return Promise.reject(error);
  },
);

export function getStoredToken() {
  return localStorage.getItem(TOKEN_STORAGE_KEY);
}

export function setStoredToken(token) {
  localStorage.setItem(TOKEN_STORAGE_KEY, token);
}

export function clearStoredToken() {
  localStorage.removeItem(TOKEN_STORAGE_KEY);
}

export default apiClient;
