import { apiClient } from "./client";
import type { Connector } from "@/types/business";

export async function getConnectors(): Promise<Connector[]> {
  const { data } = await apiClient.get<{ data: Connector[] }>("/connectors");
  return data.data;
}

export async function configureConnector(payload: {
  connector_id: string;
  values: Array<{ key: string; value: unknown; value_type: string; is_secret: boolean }>;
  default_owner_id?: string | null;
}): Promise<{
  connector_id: string;
  configured_keys: string[];
  key_version: string;
  default_owner_id: string | null;
}> {
  const { data } = await apiClient.post("/connectors/config", payload);
  return data;
}

export interface WhatsAppConfigStatus {
  connector_id: string;
  adapter: string;
  configured_keys: string[];
  required_keys: string[];
  webhook_url: string;
  default_owner_id: string | null;
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

export interface FeishuConfigStatus {
  connector_id: string;
  configured_keys: string[];
  status: string;
  health_status: string | null;
  last_health_check_at: string | null;
}

export interface FeishuTestResult {
  success: boolean;
  message: string;
  message_id: string | null;
}

export async function getFeishuConfigStatus(
  connectorId: string,
): Promise<FeishuConfigStatus> {
  const { data } = await apiClient.get<FeishuConfigStatus>(
    `/connectors/feishu/${connectorId}/config-status`,
  );
  return data;
}

export async function testFeishuConnector(): Promise<FeishuTestResult> {
  const { data } = await apiClient.post<FeishuTestResult>("/connectors/feishu/test");
  return data;
}

export async function getFeishuOAuthUrl(
  userId: string,
): Promise<{ url: string; expires_in: number }> {
  const { data } = await apiClient.get<{ url: string; expires_in: number }>(
    "/connectors/feishu/oauth/url",
    { params: { user_id: userId } },
  );
  return data;
}
