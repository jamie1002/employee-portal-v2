import apiClient from "./client";

export async function getRooms() {
  const { data } = await apiClient.get("/rooms");
  return data;
}

export async function getRoomBookings(params) {
  const { data } = await apiClient.get("/room-bookings", { params });
  return data;
}

export async function createRoomBooking(payload) {
  const { data } = await apiClient.post("/room-bookings", payload);
  return data;
}

export async function cancelRoomBooking(bookingId) {
  const { data } = await apiClient.patch(`/room-bookings/${bookingId}/cancel`);
  return data;
}

export async function forceReleaseRoomBooking(bookingId) {
  const { data } = await apiClient.delete(`/room-bookings/${bookingId}`);
  return data;
}
