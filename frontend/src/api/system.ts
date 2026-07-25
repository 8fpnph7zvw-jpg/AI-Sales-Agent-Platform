import { apiClient } from "./client";
import type { SystemConfig } from "@/types/business";

export async function getSystemConfigs(): Promise<SystemConfig[]> {
  const { data } = await apiClient.get<{ data: SystemConfig[] }>("/system/configs");
  return data.data;
}

export async function updateSystemConfig(
  key: string,
  value: unknown,
): Promise<SystemConfig> {
  const { data } = await apiClient.put<SystemConfig>(`/system/configs/${key}`, { value });
  return data;
}
