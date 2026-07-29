import { apiClient } from "./client";
import type { AuthUser, LoginRequest, LoginResponse } from "@/types/auth";

export async function login(payload: LoginRequest): Promise<LoginResponse> {
  const { data } = await apiClient.post<LoginResponse>("/auth/login", payload);
  return data;
}

export async function refreshAccessToken(refreshToken: string): Promise<LoginResponse> {
  const { data } = await apiClient.post<LoginResponse>("/auth/refresh", {
    refresh_token: refreshToken,
  });
  return data;
}

export async function revokeRefreshToken(refreshToken: string): Promise<void> {
  await apiClient.post("/auth/logout", { refresh_token: refreshToken });
}

export async function getCurrentUser(): Promise<AuthUser> {
  const { data } = await apiClient.get<AuthUser>("/auth/me");
  return data;
}
