import { apiClient } from "./client";
import type { SalesUser, SalesUserCreate, SalesUserUpdate } from "@/types/business";

export async function getUsers(): Promise<{ data: SalesUser[]; total: number }> {
  const { data } = await apiClient.get<{ data: SalesUser[]; total: number }>("/users");
  return data;
}

export async function createSalesUser(payload: SalesUserCreate): Promise<SalesUser> {
  const { data } = await apiClient.post<SalesUser>("/users", payload);
  return data;
}

export async function updateSalesUser(id: string, payload: SalesUserUpdate): Promise<SalesUser> {
  const { data } = await apiClient.patch<SalesUser>(`/users/${id}`, payload);
  return data;
}

export async function deleteSalesUser(id: string): Promise<void> {
  await apiClient.delete(`/users/${id}`);
}

export async function updateFeishuBinding(
  id: string,
  payload: { feishu_open_id: string | null; feishu_name: string | null },
): Promise<SalesUser> {
  const { data } = await apiClient.patch<SalesUser>(`/users/${id}/feishu-binding`, payload);
  return data;
}
