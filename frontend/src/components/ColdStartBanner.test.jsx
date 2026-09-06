import { act, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import apiClient from "../api/client";
import ColdStartBanner from "./ColdStartBanner";

function delayedAdapter(ms) {
  return (config) =>
    new Promise((resolve) => {
      setTimeout(() => resolve({ status: 200, statusText: "OK", headers: {}, config, data: {} }), ms);
    });
}

let originalAdapter;

beforeEach(() => {
  vi.useFakeTimers();
  originalAdapter = apiClient.defaults.adapter;
});

afterEach(() => {
  apiClient.defaults.adapter = originalAdapter;
  vi.useRealTimers();
});

test("請求逾 3 秒 → 橫幅出現；請求完成 → 橫幅消失", async () => {
  apiClient.defaults.adapter = delayedAdapter(5000);
  render(<ColdStartBanner />);

  expect(screen.queryByRole("status")).not.toBeInTheDocument();

  const requestPromise = apiClient.get("/slow");

  await act(async () => {
    await vi.advanceTimersByTimeAsync(3000);
  });
  expect(screen.getByRole("status")).toBeInTheDocument();

  await act(async () => {
    await vi.advanceTimersByTimeAsync(2000);
    await requestPromise;
  });
  expect(screen.queryByRole("status")).not.toBeInTheDocument();
});

test("請求 3 秒內完成 → 橫幅從未出現", async () => {
  apiClient.defaults.adapter = delayedAdapter(1000);
  render(<ColdStartBanner />);

  const requestPromise = apiClient.get("/fast");

  await act(async () => {
    await vi.advanceTimersByTimeAsync(1000);
    await requestPromise;
  });
  expect(screen.queryByRole("status")).not.toBeInTheDocument();

  await act(async () => {
    await vi.advanceTimersByTimeAsync(3000);
  });
  expect(screen.queryByRole("status")).not.toBeInTheDocument();
});

test("兩個並行慢請求 → 僅顯示一個橫幅，且第一個完成時橫幅不消失，兩個都完成才消失", async () => {
  apiClient.defaults.adapter = delayedAdapter(4000);
  render(<ColdStartBanner />);

  const firstRequest = apiClient.get("/slow-1");

  apiClient.defaults.adapter = delayedAdapter(6000);
  const secondRequest = apiClient.get("/slow-2");

  await act(async () => {
    await vi.advanceTimersByTimeAsync(3000);
  });
  expect(screen.getAllByRole("status")).toHaveLength(1);

  await act(async () => {
    await vi.advanceTimersByTimeAsync(1000);
    await firstRequest;
  });
  expect(screen.getByRole("status")).toBeInTheDocument();

  await act(async () => {
    await vi.advanceTimersByTimeAsync(2000);
    await secondRequest;
  });
  expect(screen.queryByRole("status")).not.toBeInTheDocument();
});
