import type { AuthSession } from "@/types/auth";

const AUTH_STORAGE_KEY = "ai-sales-agent.auth";

export function readAuthSession(): AuthSession | null {
  const raw = sessionStorage.getItem(AUTH_STORAGE_KEY);
  if (!raw) return null;

  try {
    const session = JSON.parse(raw) as AuthSession;
    if (!session.token || session.expiresAt <= Date.now()) {
      sessionStorage.removeItem(AUTH_STORAGE_KEY);
      return null;
    }
    return session;
  } catch {
    sessionStorage.removeItem(AUTH_STORAGE_KEY);
    return null;
  }
}

export function writeAuthSession(session: AuthSession): void {
  sessionStorage.setItem(AUTH_STORAGE_KEY, JSON.stringify(session));
}

export function clearAuthSession(): void {
  sessionStorage.removeItem(AUTH_STORAGE_KEY);
}
