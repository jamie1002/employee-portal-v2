import apiClient from "./client";

export async function punchIn() {
  const { data } = await apiClient.post("/attendance/punch-in");
  return data;
}

export async function punchOut() {
  const { data } = await apiClient.post("/attendance/punch-out");
  return data;
}

export async function getToday() {
  const { data } = await apiClient.get("/attendance/today");
  return data;
}

export async function markTodayNote() {
  const { data } = await apiClient.post("/attendance/today/note");
  return data;
}

export async function getMyRecords(params) {
  const { data } = await apiClient.get("/attendance/me", { params });
  return data;
}

export async function getCompanyRecords(params) {
  const { data } = await apiClient.get("/attendance", { params });
  return data;
}
