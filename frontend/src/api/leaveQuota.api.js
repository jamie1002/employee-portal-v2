import apiClient from "./client";

export async function getMyLeaveQuota() {
  const { data } = await apiClient.get("/leave-quota/me");
  return data;
}
