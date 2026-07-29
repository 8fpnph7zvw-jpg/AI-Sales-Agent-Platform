export interface AuthUser {
  id: string;
  tenant_id: string;
  display_name: string;
  email: string;
  permissions: string[];
}

export interface LoginRequest {
  tenant_slug: string;
  email: string;
  password: string;
}

export interface LoginResponse {
  access_token: string;
  refresh_token: string;
  token_type: "bearer";
  expires_in: number;
  refresh_expires_in: number;
  user: AuthUser;
}

export interface AuthSession {
  token: string;
  refreshToken: string;
  expiresAt: number;
  refreshExpiresAt: number;
  user: AuthUser;
}
