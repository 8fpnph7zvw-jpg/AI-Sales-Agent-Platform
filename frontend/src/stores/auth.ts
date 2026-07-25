import { computed, ref } from "vue";
import { defineStore } from "pinia";

import { login as loginRequest } from "@/api/auth";
import type { AuthSession, AuthUser, LoginRequest } from "@/types/auth";
import {
  clearAuthSession,
  readAuthSession,
  writeAuthSession,
} from "@/utils/auth-storage";

export const useAuthStore = defineStore("auth", () => {
  const initial = readAuthSession();
  const token = ref<string | null>(initial?.token ?? null);
  const expiresAt = ref<number | null>(initial?.expiresAt ?? null);
  const user = ref<AuthUser | null>(initial?.user ?? null);

  const isAuthenticated = computed(
    () => Boolean(token.value && user.value && (expiresAt.value ?? 0) > Date.now()),
  );
  const permissionSet = computed(() => new Set(user.value?.permissions ?? []));

  function canAny(permissions: string[] = []): boolean {
    return permissions.length === 0 || permissions.some((item) => permissionSet.value.has(item));
  }

  function canAll(permissions: string[] = []): boolean {
    return permissions.every((item) => permissionSet.value.has(item));
  }

  async function login(payload: LoginRequest): Promise<void> {
    const response = await loginRequest(payload);
    const session: AuthSession = {
      token: response.access_token,
      expiresAt: Date.now() + response.expires_in * 1000,
      user: response.user,
    };
    token.value = session.token;
    expiresAt.value = session.expiresAt;
    user.value = session.user;
    writeAuthSession(session);
  }

  function logout(): void {
    token.value = null;
    expiresAt.value = null;
    user.value = null;
    clearAuthSession();
  }

  return {
    token,
    user,
    expiresAt,
    isAuthenticated,
    permissionSet,
    canAny,
    canAll,
    login,
    logout,
  };
});
