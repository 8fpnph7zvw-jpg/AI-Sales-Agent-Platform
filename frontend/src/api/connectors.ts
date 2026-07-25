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
