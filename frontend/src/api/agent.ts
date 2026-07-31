import { apiClient } from "./client";
import type { AgentChatResult } from "@/types/business";

export async function chatWithAgent(payload: {
  conversation_id: string;
  query: string;
  idempotency_key: string;
  inputs?: Record<string, unknown>;
}): Promise<AgentChatResult> {
  const { data } = await apiClient.post<AgentChatResult>("/agent/chat", payload, {
    // Agent inference can legitimately take longer than normal CRUD requests.
    timeout: 90_000,
  });
  return data;
}
