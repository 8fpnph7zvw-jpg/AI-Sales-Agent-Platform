import { apiClient } from "./client";
import type { PageResult } from "@/types/api";
import type { Conversation, Message } from "@/types/business";

export async function getConversations(params: {
  limit: number;
  offset: number;
  status?: string;
  search?: string;
}): Promise<PageResult<Conversation>> {
  const { data } = await apiClient.get<PageResult<Conversation>>("/conversations", { params });
  return data;
}

export async function createConversation(payload: {
  customer_id: string;
  subject?: string;
}): Promise<Conversation> {
  const { data } = await apiClient.post<Conversation>("/conversations", payload);
  return data;
}

export async function getConversationMessages(
  conversationId: string,
  params: { limit?: number; before_sequence?: number } = {},
): Promise<PageResult<Message>> {
  const { data } = await apiClient.get<PageResult<Message>>(
    `/conversations/${conversationId}/messages`,
    { params },
  );
  return data;
}

export async function sendConversationMessage(payload: {
  conversation_id: string;
  content: string;
  message_type: string;
  idempotency_key: string;
}): Promise<Message> {
  const { data } = await apiClient.post<Message>("/conversation/message", payload);
  return data;
}

export async function deleteConversation(conversationId: string): Promise<void> {
  await apiClient.delete(`/conversations/${conversationId}`);
}
