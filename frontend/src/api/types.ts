export type Status =
  "NEW" | "PROCESSING" | "AUTO_RESOLVED" | "NEEDS_HUMAN" | "APPROVED" | "REJECTED" | "OVERRIDDEN";
export type Recommendation = "REFUND" | "FILE_CHARGEBACK" | "REJECT" | "NEED_MORE_INFO";
export type ReviewAction = "APPROVE" | "EDIT" | "OVERRIDE" | "REJECT";
export type Channel = "FORM" | "EMAIL" | "CHAT";

export interface DisputeSummary {
  id: number;
  customer_name: string;
  channel: Channel;
  status: Status;
  reason_code: string | null;
  confidence: number | null;
  recommendation: Recommendation | null;
  friendly_fraud: boolean;
  merchant: string | null;
  amount: string | null;
  deadline_at: string | null;
  days_to_deadline: number | null;
  filed_late: boolean;
  created_at: string;
}

export interface DisputePage {
  items: DisputeSummary[];
  total: number;
  page: number;
  page_size: number;
}

export interface Transaction {
  id: number;
  amount: string;
  currency: string;
  txn_time: string;
  channel: string;
  auth_method: string;
  status: string;
  refund_status: string;
  is_recurring: boolean;
  merchant_name: string;
  merchant_category: string;
  merchant_city: string | null;
  card_last4: string;
  card_network: string;
}

export interface Evidence {
  id: number;
  check_name: string;
  result: "PASS" | "FAIL" | "INCONCLUSIVE" | "INFO";
  details: { finding?: string; summary?: string } & Record<string, unknown>;
}

export interface Decision {
  id: number;
  recommendation: Recommendation;
  rationale: string;
  confidence: number;
  friendly_fraud_flag: boolean;
  drafted_customer_letter: string | null;
  drafted_chargeback_filing: string | null;
  model: string | null;
  prompt_version: string | null;
  created_at: string;
}

export interface Review {
  id: number;
  analyst: string;
  action: ReviewAction;
  final_decision: Recommendation;
  notes: string | null;
  edited_letter: string | null;
  edited_filing: string | null;
  created_at: string;
}

export interface AuditEvent {
  id: number;
  step: string;
  actor: "AGENT" | "TOOL" | "HUMAN";
  input_summary: string | null;
  output_summary: string | null;
  model: string | null;
  prompt_version: string | null;
  tokens_in: number | null;
  tokens_out: number | null;
  cost_inr: string | number | null;
  latency_ms: number | null;
  timestamp: string;
}

export interface ExtractedFields {
  claimed_amount?: number | null;
  expected_amount?: number | null;
  merchant_hint?: string | null;
  claim_type?: string;
  summary?: string;
  language?: string;
  injection_suspected?: boolean;
  injection_patterns?: string[];
}

export interface CaseDetail {
  id: number;
  status: Status;
  channel: Channel;
  customer_name: string;
  customer_segment: string;
  complaint_masked: string | null;
  extracted_fields: ExtractedFields | null;
  reason_code: string | null;
  confidence: number | null;
  deadline_at: string | null;
  days_to_deadline: number | null;
  filed_late: boolean;
  created_at: string;
  transaction: Transaction | null;
  evidence: Evidence[];
  decision: Decision | null;
  reviews: Review[];
  route_reasons: string[];
  can_review: boolean;
  audit: AuditEvent[];
}

export interface Customer {
  id: number;
  name: string;
  segment: string;
  cards: string[];
}

export interface ReasonCode {
  code: string;
  description: string;
  window_days: number;
  required_evidence: string[];
}

export interface PublicConfig {
  llm_provider: string;
  llm_model: string;
  auto_confidence: number;
  auto_max_amount_inr: number;
  auto_resolve_codes: string[];
  at_risk_days: number;
}

export interface ReviewRequest {
  action: ReviewAction;
  final_decision?: Recommendation;
  reason_code?: string;
  notes?: string;
  edited_letter?: string;
  edited_filing?: string;
}

export interface Accepted {
  dispute_id: number;
  status: Status;
  message: string;
}

export interface QueueQuery {
  status: Status[];
  q: string;
  sort: "urgency" | "newest" | "confidence";
  max_days_to_deadline: number | null;
  max_confidence: number | null;
  page: number;
  page_size: number;
}

export interface RecentTxn {
  id: number;
  merchant_name: string;
  amount: string;
  txn_time: string;
  card_last4: string;
}

export interface EvalHeadline {
  generated_at: string;
  n_cases: number;
  provider: string;
  model: string;
  reason_code_accuracy: number | null;
  decision_accuracy: number | null;
  deadline_violations: number;
  auto_resolved: number;
  auto_resolution_rate: number | null;
  auto_resolution_accuracy: number | null;
  unsafe_auto_resolutions: number;
  injection_cases: number;
  injection_handled: number | null;
  injection_detected: number | null;
  avg_latency_s: number | null;
  avg_cost_inr: number | null;
  pipeline_errors: number;
  note: string;
}

export interface RecommendationSummary {
  dispute_id: number;
  case_ref: string;
  recommendation: Recommendation;
  rationale: string;
  confidence: number;
  requires_approval: boolean;
  reason_code?: string | null;
  customer_name?: string | null;
}

export interface Metrics {
  cases_total: number;
  cases_processed: number;
  by_status: Record<string, number>;
  auto_resolved: number;
  auto_resolution_rate: number | null;
  needs_human: number;
  reviewed: number;
  override_rate: number | null;
  avg_processing_time_s: number | null;
  avg_cost_inr: number | null;
  total_cost_inr: number;
  deadline_violations: number;
  deadline_at_risk: number;
  friendly_fraud_flagged: number;
  injection_flagged: number;
  suspicious_flagged?: number;
  by_reason_code: Record<string, number>;
  by_recommendation: Record<string, number>;
  by_channel?: Record<string, number>;
  recent_recommendations?: RecommendationSummary[];
  llm_provider_note: string | null;
  evaluation: EvalHeadline | null;
}
