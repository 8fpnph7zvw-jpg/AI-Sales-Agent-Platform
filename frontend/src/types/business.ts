import type { PageResult } from "./api";

export interface Customer {
  id: string;
  name: string;
  company_name: string | null;
  email: string | null;
  phone_e164: string | null;
  country_code: string | null;
  language: string | null;
  lifecycle_stage: string;
  intent_score: string | null;
  intent_level: string | null;
  score_explanation: Record<string, unknown> | null;
  source_type: string | null;
  source_ref: string | null;
  tags: string[];
  owner_user_id: number | null;
  do_not_contact: boolean;
  last_contact_at: string | null;
  notes: string | null;
  created_at: string;
  updated_at: string;
}

export interface CustomerCreate {
  name: string;
  company_name?: string;
  email?: string;
  phone_e164?: string;
  country_code?: string;
  language?: string;
  source_type?: string;
  source_ref?: string;
  tags: string[];
  notes?: string;
}

export type CustomerPage = PageResult<Customer>;

export interface Conversation {
  id: string;
  customer_id: string;
  customer_name?: string;
  channel: string;
  status: string;
  ai_status: string;
  last_message_preview?: string;
  last_message_at: string | null;
  unread_count: number;
  created_at: string;
}

export interface Message {
  id: string;
  conversation_id: string;
  sequence_no: number;
  direction: string;
  sender_type: string;
  message_type: string;
  content: string;
  status: string;
  duplicate?: boolean;
  created_at: string;
}

export interface AgentChatResult {
  run_id: string;
  conversation_id: string;
  message_id: string;
  answer: string;
  dify_conversation_id: string | null;
  citations: Array<Record<string, unknown>>;
  usage: {
    prompt_tokens: number | null;
    completion_tokens: number | null;
    cost_amount: string | null;
    cost_currency: string | null;
    latency_ms: number | null;
  };
  duplicate: boolean;
}

export interface LeadScoreResult {
  customer_id: string;
  score: number;
  level: string;
  components: Record<string, number>;
  scoring_version: string;
}

export interface KnowledgeFile {
  id: string;
  filename: string;
  collection_name: string;
  status: string;
  chunk_count: number;
  size_bytes: number;
  updated_at: string;
}

export interface QuotationItemInput {
  product_id?: string;
  sku?: string;
  name?: string;
  description?: string;
  quantity: number;
  unit?: string;
  unit_price?: number;
  discount_rate: number;
  tax_rate: number;
}

export interface QuotationCreate {
  customer_id: string;
  conversation_id?: string;
  currency: string;
  valid_until?: string;
  incoterm?: string;
  payment_terms?: string;
  notes?: string;
  shipping_amount: number;
  items: QuotationItemInput[];
}

export interface Quotation {
  id: string;
  quotation_no: string;
  customer_id: string;
  customer_name?: string;
  status: string;
  currency: string;
  subtotal: string;
  discount_amount: string;
  tax_amount: string;
  shipping_amount: string;
  total_amount: string;
  valid_until: string | null;
  items?: Array<QuotationItemInput & { line_total: string }>;
  created_at: string;
}

export interface Product {
  id: string;
  sku: string;
  name: string;
  description: string | null;
  category: string | null;
  unit: string;
  currency: string;
  base_price: string;
  min_order_qty: string | null;
  status: string;
  created_at: string;
}

export interface Connector {
  id: string;
  provider: string;
  name: string;
  status: string;
  capabilities: string[];
  external_account_id: string;
  health_status: string | null;
  last_health_check_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface Workflow {
  id: string;
  name: string;
  description: string | null;
  status: string;
  version: number;
  trigger_type: string;
  updated_at: string;
}

export interface SystemConfig {
  key: string;
  value: unknown;
  value_type: string;
  is_secret: boolean;
  updated_at: string;
}

export interface DashboardSummary {
  customer_total: number;
  active_conversations: number;
  high_intent_customers: number;
  pending_quotations: number;
  ai_resolution_rate: number;
  average_response_seconds: number;
  trend: Array<{ date: string; inquiries: number; ai_replies: number }>;
  recent_activities: Array<{
    id: string;
    type: string;
    title: string;
    occurred_at: string;
  }>;
}
