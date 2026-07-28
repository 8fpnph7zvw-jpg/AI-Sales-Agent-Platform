import { apiClient } from "./client";
import type { Connector } from "@/types/business";

export async function getConnectors(): Promise<Connector[]> {
  const { data } = await apiClient.get<{ data: Connector[] }>("/connectors");
  return data.data;
}

export async function configureConnector(payload: {
  connector_id: string;
  values: Array<{ key: string; value: unknown; value_type: string; is_secret: boolean }>;
}): Promise<{ connector_id: string; configured_keys: string[]; key_version: string }> {
  const { data } = await apiClient.post("/connectors/config", payload);
  return data;
}

export interface WhatsAppConfigStatus {
  connector_id: string;
  configured_keys: string[];
  required_keys: string[];
  webhook_url: string;
}

export interface WhatsAppTestResult {
  connector_id: string;
  status: string;
  message: string;
  latency_ms: number | null;
  checked_at: string;
}

export async function getWhatsAppConfigStatus(
  connectorId: string,
): Promise<WhatsAppConfigStatus> {
  const { data } = await apiClient.get<WhatsAppConfigStatus>(
    `/connectors/whatsapp/${connectorId}/config-status`,
  );
  return data;
}

export async function testWhatsAppConnector(
  connectorId: string,
): Promise<WhatsAppTestResult> {
  const { data } = await apiClient.post<WhatsAppTestResult>(
    "/connectors/whatsapp/test",
    { connector_id: connectorId },
  );
  return data;
}

export interface OpenWAStatus {
  session_id: string | null;
  name: string | null;
  status: string;
  api_key_configured: boolean;
  qr_available: boolean;
  phone_number: string | null;
}

export interface OpenWAQRCode {
  session_id: string;
  status: string;
  data_url: string | null;
  message: string;
}

export async function getOpenWAStatus(): Promise<OpenWAStatus> {
  const { data } = await apiClient.get<OpenWAStatus>("/connectors/whatsapp/status");
  return data;
}

export async function createOpenWASession(): Promise<OpenWAStatus> {
  const { data } = await apiClient.post<OpenWAStatus>("/connectors/whatsapp/session");
  return data;
}

export async function deleteOpenWASession(): Promise<OpenWAStatus> {
  const { data } = await apiClient.delete<OpenWAStatus>("/connectors/whatsapp/session");
  return data;
}

export async function getOpenWAQRCode(): Promise<OpenWAQRCode> {
  const { data } = await apiClient.get<OpenWAQRCode>("/connectors/whatsapp/qrcode");
  return data;
}

export async function reconnectOpenWA(): Promise<OpenWAStatus> {
  const { data } = await apiClient.post<OpenWAStatus>("/connectors/whatsapp/reconnect");
  return data;
}
