import apiClient from "./client";

export async function getHolidays() {
  const { data } = await apiClient.get("/holidays");
  return data;
}

export async function createHoliday(payload) {
  const { data } = await apiClient.post("/holidays", payload);
  return data;
}

export async function deleteHoliday(holidayDate) {
  await apiClient.delete(`/holidays/${holidayDate}`);
}
