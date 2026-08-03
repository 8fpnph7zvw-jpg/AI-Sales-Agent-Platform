import { apiClient } from "./client";
import type {
  CustomerCurrentScorePage,
  CustomerScore,
  CustomerScorePage,
  LeadScoreResult,
} from "@/types/business";

export interface ScoreSignals {
  need_clarity: number;
  budget_match: number;
  urgency: number;
  engagement: number;
  profile_fit: number;
}

export async function calculateLeadScore(
  customerId: string,
  signals: ScoreSignals,
): Promise<LeadScoreResult> {
  const { data } = await apiClient.post<LeadScoreResult>("/lead-score", {
    customer_id: customerId,
    signals,
  });
  return data;
}

export async function getLeadScores(params: {
  limit: number;
  offset: number;
  customer_id?: string;
}): Promise<CustomerCurrentScorePage> {
  const { data } = await apiClient.get<CustomerCurrentScorePage>("/lead-scores", { params });
  return data;
}

export async function getLeadScoreHistory(
  customerId: string,
  params: { limit: number; offset: number },
): Promise<CustomerScorePage> {
  const { data } = await apiClient.get<CustomerScorePage>(
    `/lead-scores/${customerId}/history`,
    { params },
  );
  return data;
}

export async function deleteLeadScoreHistory(
  customerId: string,
  scoreId: number,
): Promise<void> {
  await apiClient.delete(`/lead-scores/${customerId}/history/${scoreId}`);
}

export async function runLeadScoringWorkflow(payload: {
  customer_id: string;
  product_requirement?: string;
  quantity?: string;
}): Promise<CustomerScore> {
  const { data } = await apiClient.post<CustomerScore>("/lead-scores/run", payload);
  return data;
}
