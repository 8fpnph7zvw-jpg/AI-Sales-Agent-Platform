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
