import apiClient from "./client";

export async function getAttendanceChanges(params) {
  const { data } = await apiClient.get("/attendance/changes", { params });
  return data;
}
