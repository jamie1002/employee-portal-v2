import apiClient from "./client";

export async function createPunchRequest(payload) {
  const { data } = await apiClient.post("/punch-requests", payload);
  return data;
}

export async function getMyPunchRequests(params) {
  const { data } = await apiClient.get("/punch-requests/me", { params });
  return data;
}

export async function getPendingPunchRequests() {
  const { data } = await apiClient.get("/punch-requests/pending");
  return data;
}

export async function reviewPunchRequest(requestId, payload) {
  const { data } = await apiClient.patch(`/punch-requests/${requestId}/review`, payload);
  return data;
}

export async function createLeaveRequest(payload) {
  const { data } = await apiClient.post("/leave-requests", payload);
  return data;
}

export async function getMyLeaveRequests(params) {
  const { data } = await apiClient.get("/leave-requests/me", { params });
  return data;
}

export async function getPendingLeaveRequests() {
  const { data } = await apiClient.get("/leave-requests/pending");
  return data;
}

export async function reviewLeaveRequest(requestId, payload) {
  const { data } = await apiClient.patch(`/leave-requests/${requestId}/review`, payload);
  return data;
}

export async function createOvertimeRequest(payload) {
  const { data } = await apiClient.post("/overtime-requests", payload);
  return data;
}

export async function getMyOvertimeRequests(params) {
  const { data } = await apiClient.get("/overtime-requests/me", { params });
  return data;
}

export async function getPendingOvertimeRequests() {
  const { data } = await apiClient.get("/overtime-requests/pending");
  return data;
}

export async function reviewOvertimeRequest(requestId, payload) {
  const { data } = await apiClient.patch(`/overtime-requests/${requestId}/review`, payload);
  return data;
}
