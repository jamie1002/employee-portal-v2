import apiClient from "./client";

export async function askChat(question) {
  const { data } = await apiClient.post(
    "/chat",
    { question },
    { skipSlowRequestTracking: true },
  );
  return data;
}
