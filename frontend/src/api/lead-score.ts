import { apiClient } from "./client";
import type { CustomerScore, CustomerScorePage, LeadScoreResult } from "@/types/business";

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
}): Promise<CustomerScorePage> {
  const { data } = await apiClient.get<CustomerScorePage>("/lead-scores", { params });
  return data;
}

export async function runLeadScoringWorkflow(payload: {
  customer_id: string;
  product_requirement?: string;
  quantity?: string;
}): Promise<CustomerScore> {
  const { data } = await apiClient.post<CustomerScore>("/lead-scores/run", payload);
  return data;
}
