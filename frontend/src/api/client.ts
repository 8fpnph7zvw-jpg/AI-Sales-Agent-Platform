import axios, { AxiosError } from "axios";

import type { ApiErrorBody } from "@/types/api";
import type { AuthSession, LoginResponse } from "@/types/auth";
import {
  clearAuthSession,
  isAuthSessionRemembered,
  readAuthSession,
  writeAuthSession,
} from "@/utils/auth-storage";
import { createUuid } from "@/utils/uuid";

const baseURL = import.meta.env.VITE_API_BASE_URL || "/api/v1";

export const apiClient = axios.create({
  baseURL,
  timeout: 30_000,
  headers: {
    "Content-Type": "application/json",
  },
});

const refreshClient = axios.create({
  baseURL,
  timeout: 30_000,
  headers: { "Content-Type": "application/json" },
});

type RetryableRequest = NonNullable<AxiosError["config"]> & { _authRetry?: boolean };
let refreshRequest: Promise<AuthSession> | null = null;

apiClient.interceptors.request.use((config) => {
  const session = readAuthSession();
  if (session) {
    config.headers.Authorization = `Bearer ${session.token}`;
  }
  config.headers["X-Request-ID"] = createUuid();
  return config;
});

apiClient.interceptors.response.use(
  (response) => response,
  async (error: AxiosError<ApiErrorBody>) => {
    const request = error.config as RetryableRequest | undefined;
    const isTokenEndpoint =
      request?.url?.includes("/auth/login") || request?.url?.includes("/auth/refresh");
    if (error.response?.status !== 401 || !request || isTokenEndpoint) {
      return Promise.reject(error);
    }
    if (request._authRetry) {
      clearAuthSession();
      window.dispatchEvent(new CustomEvent("auth:expired"));
      return Promise.reject(error);
    }

    request._authRetry = true;
    try {
      const session = await refreshAuthSession();
      request.headers.Authorization = `Bearer ${session.token}`;
      return await apiClient.request(request);
    } catch (refreshError) {
      clearAuthSession();
      window.dispatchEvent(new CustomEvent("auth:expired"));
      return Promise.reject(refreshError);
    }
  },
);

async function refreshAuthSession(): Promise<AuthSession> {
  if (refreshRequest) return refreshRequest;
  const current = readAuthSession();
  if (!current?.refreshToken) throw new Error("No refresh token is available.");
  const remembered = isAuthSessionRemembered();

  refreshRequest = (async () => {
    const { data } = await refreshClient.post<LoginResponse>("/auth/refresh", {
      refresh_token: current.refreshToken,
    });
    const next: AuthSession = {
      token: data.access_token,
      refreshToken: data.refresh_token,
      expiresAt: Date.now() + data.expires_in * 1000,
      refreshExpiresAt: Date.now() + data.refresh_expires_in * 1000,
      user: data.user,
    };
    writeAuthSession(next, remembered);
    window.dispatchEvent(new CustomEvent<AuthSession>("auth:refreshed", { detail: next }));
    return next;
  })().finally(() => {
    refreshRequest = null;
  });
  return refreshRequest;
}

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
