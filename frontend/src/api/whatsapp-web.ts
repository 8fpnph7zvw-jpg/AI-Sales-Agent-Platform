import { apiClient, getApiErrorMessage } from "./client";
import { configureConnector } from "./connectors";

export type WhatsAppWebStatus =
  | "WAITING_QR"
  | "CONNECTING"
  | "CONNECTED"
  | "DISCONNECTED";

export interface WhatsAppWebSessionStatus {
  connector_id: string;
  session_id: string;
  status: WhatsAppWebStatus;
  phone: string | null;
  last_error: string | null;
}

export interface WhatsAppWebQr extends WhatsAppWebSessionStatus {
  qr: string | null;
  data_url: string | null;
}

export async function saveWhatsAppWebConfig(
  connectorId: string,
  sessionId: string,
): Promise<void> {
  await configureConnector({
    connector_id: connectorId,
    values: [
      { key: "adapter", value: "webjs_gateway", value_type: "string", is_secret: false },
      { key: "session_id", value: sessionId, value_type: "string", is_secret: false },
    ],
  });
}

export async function connectWhatsAppWeb(
  connectorId: string,
): Promise<WhatsAppWebSessionStatus> {
  const { data } = await apiClient.post<WhatsAppWebSessionStatus>(
    `/connectors/whatsapp/${connectorId}/web-session/connect`,
  );
  return data;
}

export async function getWhatsAppWebStatus(
  connectorId: string,
): Promise<WhatsAppWebSessionStatus> {
  const { data } = await apiClient.get<WhatsAppWebSessionStatus>(
    `/connectors/whatsapp/${connectorId}/web-session/status`,
  );
  return data;
}

export async function getWhatsAppWebQr(connectorId: string): Promise<WhatsAppWebQr> {
  const { data } = await apiClient.get<WhatsAppWebQr>(
    `/connectors/whatsapp/${connectorId}/web-session/qr`,
  );
  return data;
}

export async function reconnectWhatsAppWeb(
  connectorId: string,
): Promise<WhatsAppWebSessionStatus> {
  const { data } = await apiClient.post<WhatsAppWebSessionStatus>(
    `/connectors/whatsapp/${connectorId}/web-session/reconnect`,
  );
  return data;
}

export async function disconnectWhatsAppWeb(
  connectorId: string,
): Promise<WhatsAppWebSessionStatus> {
  const { data } = await apiClient.delete<WhatsAppWebSessionStatus>(
    `/connectors/whatsapp/${connectorId}/web-session`,
  );
  return data;
}

export function getWhatsAppWebErrorMessage(error: unknown): string {
  return getApiErrorMessage(error);
}
