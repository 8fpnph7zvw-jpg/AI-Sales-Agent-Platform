import { apiClient } from "./client";
import type { PageResult } from "@/types/api";
import type { Workflow } from "@/types/business";

export async function getWorkflows(params: {
  limit: number;
  offset: number;
  status?: string;
}): Promise<PageResult<Workflow>> {
  const { data } = await apiClient.get<PageResult<Workflow>>("/workflows", { params });
  return data;
}
