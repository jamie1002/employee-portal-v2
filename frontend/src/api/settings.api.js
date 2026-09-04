import apiClient from "./client";

export async function getSettings() {
  const { data } = await apiClient.get("/settings");
  return data;
}

export async function updateSettings(payload) {
  const { data } = await apiClient.put("/settings", payload);
  return data;
}
