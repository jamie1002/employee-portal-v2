import apiClient from "./client";

export async function getUsers(params) {
  const { data } = await apiClient.get("/users", { params });
  return data;
}

export async function createUser(payload) {
  const { data } = await apiClient.post("/users", payload);
  return data;
}

export async function updateUser(userId, payload) {
  const { data } = await apiClient.put(`/users/${userId}`, payload);
  return data;
}

export async function deleteUser(userId) {
  const { data } = await apiClient.delete(`/users/${userId}`);
  return data;
}

export async function getAllPermissions() {
  const { data } = await apiClient.get("/users/permissions");
  return data;
}

export async function setUserPermissions(userId, permissions) {
  const { data } = await apiClient.put(`/users/${userId}/permissions`, { permissions });
  return data;
}
