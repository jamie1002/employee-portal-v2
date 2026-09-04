import apiClient from "./client";

export async function getDepartments() {
  const { data } = await apiClient.get("/departments");
  return data;
}

export async function createDepartment(payload) {
  const { data } = await apiClient.post("/departments", payload);
  return data;
}

export async function updateDepartment(departmentId, payload) {
  const { data } = await apiClient.put(`/departments/${departmentId}`, payload);
  return data;
}

export async function deleteDepartment(departmentId) {
  const { data } = await apiClient.delete(`/departments/${departmentId}`);
  return data;
}
