import axios, { AxiosError } from "axios";

import type { ApiErrorBody } from "@/types/api";
import { clearAuthSession, readAuthSession } from "@/utils/auth-storage";

export const apiClient = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || "/api/v1",
  timeout: 30_000,
  headers: {
    "Content-Type": "application/json",
  },
});

apiClient.interceptors.request.use((config) => {
  const session = readAuthSession();
  if (session) {
    config.headers.Authorization = `Bearer ${session.token}`;
  }
  config.headers["X-Request-ID"] = crypto.randomUUID();
  return config;
});

apiClient.interceptors.response.use(
  (response) => response,
  (error: AxiosError<ApiErrorBody>) => {
    if (error.response?.status === 401) {
      clearAuthSession();
      window.dispatchEvent(new CustomEvent("auth:expired"));
    }
    return Promise.reject(error);
  },
);

export function getApiErrorMessage(error: unknown): string {
  if (!axios.isAxiosError<ApiErrorBody>(error)) {
    return error instanceof Error ? error.message : "请求失败，请稍后重试";
  }

  const body = error.response?.data;
  if (body?.error?.message) return body.error.message;
  if (typeof body?.detail === "string") return body.detail;
  if (Array.isArray(body?.detail)) {
    return body.detail.map((item) => item.msg).join("；");
  }
  if (error.code === "ECONNABORTED") return "请求超时，请检查网络连接";
  return error.message || "服务暂时不可用";
}
