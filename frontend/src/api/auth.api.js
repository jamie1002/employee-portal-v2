import apiClient from "./client";

export async function login(email, password) {
  const { data } = await apiClient.post("/auth/login", { email, password });
  return data;
}

export async function getMe() {
  const { data } = await apiClient.get("/auth/me");
  return data;
}

export async function changePassword(oldPassword, newPassword) {
  const { data } = await apiClient.post("/auth/change-password", { oldPassword, newPassword });
  return data;
}
