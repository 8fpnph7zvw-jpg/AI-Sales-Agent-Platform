import { computed, ref } from "vue";
import { defineStore } from "pinia";

import {
  getCurrentUser,
  login as loginRequest,
  revokeRefreshToken,
} from "@/api/auth";
import type { AuthSession, AuthUser, LoginRequest } from "@/types/auth";
import {
  clearAuthSession,
  isAuthSessionRemembered,
  readAuthSession,
  writeAuthSession,
} from "@/utils/auth-storage";

export const useAuthStore = defineStore("auth", () => {
  const initial = readAuthSession();
  const token = ref<string | null>(initial?.token ?? null);
  const expiresAt = ref<number | null>(initial?.expiresAt ?? null);
  const refreshToken = ref<string | null>(initial?.refreshToken ?? null);
  const refreshExpiresAt = ref<number | null>(initial?.refreshExpiresAt ?? null);
  const user = ref<AuthUser | null>(initial?.user ?? null);
  let sessionValidated = false;
  let validationRequest: Promise<void> | null = null;

  const isAuthenticated = computed(
    () =>
      Boolean(
        token.value &&
          refreshToken.value &&
          user.value &&
          (refreshExpiresAt.value ?? 0) > Date.now(),
      ),
  );
  const permissionSet = computed(() => new Set(user.value?.permissions ?? []));

  function canAny(permissions: string[] = []): boolean {
    return permissions.length === 0 || permissions.some((item) => permissionSet.value.has(item));
  }

  function canAll(permissions: string[] = []): boolean {
    return permissions.every((item) => permissionSet.value.has(item));
  }

  async function login(payload: LoginRequest, remember = false): Promise<void> {
    const response = await loginRequest(payload);
    const session: AuthSession = {
      token: response.access_token,
      refreshToken: response.refresh_token,
      expiresAt: Date.now() + response.expires_in * 1000,
      refreshExpiresAt: Date.now() + response.refresh_expires_in * 1000,
      user: response.user,
    };
    token.value = session.token;
    refreshToken.value = session.refreshToken;
    expiresAt.value = session.expiresAt;
    refreshExpiresAt.value = session.refreshExpiresAt;
    user.value = session.user;
    writeAuthSession(session, remember);
    sessionValidated = true;
  }

  async function restoreSession(): Promise<void> {
    if (sessionValidated || !isAuthenticated.value) return;
    if (validationRequest) return validationRequest;

    validationRequest = (async () => {
      try {
        const currentUser = await getCurrentUser();
        user.value = currentUser;
        writeAuthSession(
          {
            token: token.value as string,
            refreshToken: refreshToken.value as string,
            expiresAt: expiresAt.value as number,
            refreshExpiresAt: refreshExpiresAt.value as number,
            user: currentUser,
          },
          isAuthSessionRemembered(),
        );
        sessionValidated = true;
      } catch (error) {
        // A 401 response clears storage in the API interceptor. Network failures
        // retain the locally valid session so recovery does not force a login.
        if (!readAuthSession()) logout();
        throw error;
      } finally {
        validationRequest = null;
      }
    })();
    return validationRequest;
  }

  function logout(): void {
    const currentRefreshToken = refreshToken.value;
    token.value = null;
    refreshToken.value = null;
    expiresAt.value = null;
    refreshExpiresAt.value = null;
    user.value = null;
    clearAuthSession();
    if (currentRefreshToken) void revokeRefreshToken(currentRefreshToken).catch(() => undefined);
  }

  window.addEventListener("auth:refreshed", (event) => {
    const session = (event as CustomEvent<AuthSession>).detail;
    if (!session) return;
    token.value = session.token;
    refreshToken.value = session.refreshToken;
    expiresAt.value = session.expiresAt;
    refreshExpiresAt.value = session.refreshExpiresAt;
    user.value = session.user;
  });

  return {
    token,
    user,
    expiresAt,
    refreshExpiresAt,
    isAuthenticated,
    permissionSet,
    canAny,
    canAll,
    login,
    restoreSession,
    logout,
  };
});
