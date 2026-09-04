import apiClient from "./client";

export async function getExportPreview(kind, filters, columns) {
  const { data } = await apiClient.post(`/exports/${kind}`, { filters, columns });
  return data;
}

// 下載走 responseType: "blob"，失敗時錯誤回應本體也是 blob，呼叫端要先轉文字
// 才能解析出真正的錯誤訊息（見 docs/UI-SPEC.md §3.17）。
export async function downloadExportXlsx(kind, filters, columns) {
  const { data } = await apiClient.post(
    `/exports/${kind}`,
    { filters, columns },
    { params: { format: "xlsx" }, responseType: "blob" },
  );
  return data;
}
