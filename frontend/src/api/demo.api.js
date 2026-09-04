import apiClient from "./client";

export async function getDemoClock() {
  const { data } = await apiClient.get("/demo/clock");
  return data;
}

export async function setDemoClock(virtualNow) {
  const { data } = await apiClient.put("/demo/clock", { virtual_now: virtualNow });
  return data;
}

export async function resetDemoData() {
  const { data } = await apiClient.post("/demo/reset");
  return data;
}
