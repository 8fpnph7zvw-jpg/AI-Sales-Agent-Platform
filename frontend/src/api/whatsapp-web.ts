import axios from "axios";

export type WhatsAppWebStatus =
  | "WAITING_QR"
  | "CONNECTING"
  | "CONNECTED"
  | "DISCONNECTED";

export interface WhatsAppWebSessionStatus {
  sessionId: string;
  status: WhatsAppWebStatus;
  phone: string | null;
  lastError: string | null;
}

export interface WhatsAppWebQr extends WhatsAppWebSessionStatus {
  qr: string | null;
  dataUrl: string | null;
}

const gatewayClient = axios.create({
  baseURL: import.meta.env.VITE_WHATSAPP_GATEWAY_BASE_URL || "",
  timeout: 15_000,
  headers: { "Content-Type": "application/json" },
});

export async function connectWhatsAppWeb(
  sessionId: string,
): Promise<WhatsAppWebSessionStatus> {
  const { data } = await gatewayClient.post<WhatsAppWebSessionStatus>(
    "/api/whatsapp/connect",
    { sessionId },
  );
  return data;
}

export async function getWhatsAppWebStatus(
  sessionId: string,
): Promise<WhatsAppWebSessionStatus> {
  const { data } = await gatewayClient.get<WhatsAppWebSessionStatus>(
    "/api/whatsapp/status",
    { params: { sessionId } },
  );
  return data;
}

export async function getWhatsAppWebQr(sessionId: string): Promise<WhatsAppWebQr> {
  const { data } = await gatewayClient.get<WhatsAppWebQr>("/api/whatsapp/qr", {
    params: { sessionId },
  });
  return data;
}

export function getWhatsAppWebErrorMessage(error: unknown): string {
  if (!axios.isAxiosError(error)) {
    return error instanceof Error ? error.message : "WhatsApp Web 服务暂时不可用";
  }
  const body = error.response?.data as { error?: string } | undefined;
  if (body?.error) return body.error;
  if (error.code === "ECONNABORTED") return "连接请求超时，请稍后重试";
  if (!error.response) return "无法连接 WhatsApp Gateway，请确认服务已启动";
  return `WhatsApp Gateway 请求失败（${error.response.status}）`;
}
