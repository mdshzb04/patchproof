export const API = process.env.NEXT_PUBLIC_API_BASE || "http://127.0.0.1:8000";

export type EvidenceStep = {
  step: string;
  label: string;
  detail: string;
};

export type Finding = {
  id: string;
  rule_id: string;
  title: string;
  severity: "critical" | "high" | "medium" | "low";
  confidence: string;
  category: "security" | "reliability";
  file: string;
  line: number;
  end_line: number;
  snippet: string;
  evidence: string;
  impact: string;
  recommendation: string;
  fix_example: string;
  origin: "confirmed" | "needs_investigation";
  in_diff: boolean;
  resolved: boolean;
  bandit_id?: string | null;
  evidence_chain: EvidenceStep[];
  ai?: {
    explanation: string;
    why_risky: string;
    scenario: string;
    recommended_fix: string;
    corrected_code: string;
    model: string;
  } | null;
};

export type ReviewFile = {
  path: string;
  added_lines: number[];
  content: string;
  skipped_reason?: string | null;
};

export type Review = {
  id: string;
  title: string;
  filename: string;
  source: string;
  created_at: string;
  mode: "diff" | "snapshot";
  stages: { name: string; ms: number; status: string; detail: string }[];
  files: ReviewFile[];
  findings: Finding[];
  pre_existing: Finding[];
  ai_status: "off" | "ok" | "unavailable";
  ai_message: string;
  notes: string[];
  rules_checked?: number;
  summary?: {
    introduced: number;
    pre_existing: number;
    unresolved: number;
    resolved: number;
    critical: number;
    high: number;
    by_severity: Record<string, number>;
  };
};

export type Stats = {
  reviews: number;
  sample_reviews: number;
  findings: number;
  critical_high: number;
  resolved: number;
  unresolved: number;
  recent: {
    id: string;
    title: string;
    filename: string;
    source: string;
    created_at: string;
    findings: number;
    pre_existing: number;
    critical_high: number;
  }[];
};

async function parse<T>(res: Response): Promise<T> {
  const body = await res.json().catch(() => ({}));
  if (!res.ok) {
    const detail = typeof body.detail === "string" ? body.detail : res.statusText;
    throw new Error(detail || "Request failed");
  }
  return body as T;
}

export async function getJSON<T>(path: string): Promise<T> {
  const res = await fetch(`${API}${path}`, { cache: "no-store" });
  return parse<T>(res);
}

export async function postJSON<T>(path: string, payload: unknown): Promise<T> {
  const res = await fetch(`${API}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return parse<T>(res);
}
