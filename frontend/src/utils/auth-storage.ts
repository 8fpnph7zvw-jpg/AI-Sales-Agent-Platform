import type { AuthSession } from "@/types/auth";

const AUTH_STORAGE_KEY = "ai-sales-agent.auth";
const REMEMBERED_LOGIN_KEY = "ai-sales-agent.remembered-login";

export interface RememberedLogin {
  tenantSlug: string;
  email: string;
}

export function readAuthSession(): AuthSession | null {
  const storage = localStorage.getItem(AUTH_STORAGE_KEY) ? localStorage : sessionStorage;
  const raw = storage.getItem(AUTH_STORAGE_KEY);
  if (!raw) return null;

  try {
    const session = JSON.parse(raw) as AuthSession;
    if (!session.token || session.expiresAt <= Date.now()) {
      storage.removeItem(AUTH_STORAGE_KEY);
      return null;
    }
    return session;
  } catch {
    storage.removeItem(AUTH_STORAGE_KEY);
    return null;
  }
}

export function writeAuthSession(session: AuthSession, remember: boolean): void {
  clearAuthSession();
  const storage = remember ? localStorage : sessionStorage;
  storage.setItem(AUTH_STORAGE_KEY, JSON.stringify(session));
}

export function isAuthSessionRemembered(): boolean {
  return localStorage.getItem(AUTH_STORAGE_KEY) !== null;
}

export function clearAuthSession(): void {
  sessionStorage.removeItem(AUTH_STORAGE_KEY);
  localStorage.removeItem(AUTH_STORAGE_KEY);
}

export function readRememberedLogin(): RememberedLogin | null {
  const raw = localStorage.getItem(REMEMBERED_LOGIN_KEY);
  if (!raw) return null;

  try {
    const value = JSON.parse(raw) as RememberedLogin;
    return value.tenantSlug && value.email ? value : null;
  } catch {
    localStorage.removeItem(REMEMBERED_LOGIN_KEY);
    return null;
  }
}

export function writeRememberedLogin(login: RememberedLogin | null): void {
  if (!login) {
    localStorage.removeItem(REMEMBERED_LOGIN_KEY);
    return;
  }
  localStorage.setItem(REMEMBERED_LOGIN_KEY, JSON.stringify(login));
}
