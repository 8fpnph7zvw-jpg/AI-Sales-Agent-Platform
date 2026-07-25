import { apiClient } from "./client";
import type { LeadScoreResult } from "@/types/business";

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
