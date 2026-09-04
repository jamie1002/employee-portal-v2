import apiClient from "./client";

export async function getSchemaOverview() {
  const { data } = await apiClient.get("/admin/schema");
  return data;
}

export async function getTablePreview(table) {
  const { data } = await apiClient.get(`/admin/schema/${table}/rows`);
  return data;
}
