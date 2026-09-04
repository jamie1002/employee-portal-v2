import apiClient from "./client";

export async function getHealth() {
  const { data } = await apiClient.get("/health");
  return data;
}
