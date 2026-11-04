import type { Finding, Review } from "@/lib/api";

export function when(iso: string) {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso.replace("T", " ").replace("Z", " UTC");
  return new Intl.DateTimeFormat("en", {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

export function reviewStatus(review: Pick<Review, "findings">) {
  const open = review.findings.filter((finding) => !finding.resolved);
  if (review.findings.length === 0) return "Clear";
  if (open.length === 0) return "Resolved";
  if (open.some((finding) => finding.severity === "critical" || finding.severity === "high")) return "Needs attention";
  return "Open";
}

export function queueStatus(findings: number, criticalHigh: number) {
  if (findings === 0) return "Clear";
  if (criticalHigh > 0) return "Needs attention";
  return "Open";
}

const STEP_NAME: Record<string, string> = {
  changed_line: "Changed code",
  rule: "Detection rule",
  evidence: "Supporting evidence",
  risk: "Risk explanation",
  fix: "Recommended fix",
};

export function stepName(step: string) {
  return STEP_NAME[step] || step.replaceAll("_", " ");
}

export function reportMarkdown(review: Review) {
  const lines = [
    `# ${review.title}`,
    "",
    `- File: ${review.filename}`,
    `- Reviewed: ${review.created_at}`,
    `- Source: ${review.source}`,
    `- Mode: ${review.mode}`,
    `- Status: ${reviewStatus(review)}`,
    `- AI: ${review.ai_status}. ${review.ai_message}`,
    "",
    `Introduced findings: ${review.findings.length}. Pre-existing: ${review.pre_existing.length}.`,
    "",
  ];
  const write = (heading: string, items: Finding[]) => {
    lines.push(`## ${heading}`, "");
    if (items.length === 0) {
      lines.push("None.", "");
      return;
    }
    for (const finding of items) {
      lines.push(`### ${finding.title}`, "");
      lines.push(`- ${finding.severity} · ${finding.rule_id} · ${finding.file}:${finding.line}`);
      lines.push(`- Confidence: ${finding.confidence}`);
      lines.push(`- Origin: ${finding.origin}`);
      lines.push(`- Resolved: ${finding.resolved ? "yes" : "no"}`);
      if (finding.bandit_id) lines.push(`- Bandit: ${finding.bandit_id}`);
      lines.push("", "Evidence:", "", finding.evidence, "", "Impact:", "", finding.impact, "");
      lines.push("Recommended fix:", "", finding.recommendation, "", "```", finding.fix_example, "```", "");
      if (finding.evidence_chain.length) {
        lines.push("Why this finding exists:", "");
        for (const step of finding.evidence_chain) {
          lines.push(`- ${stepName(step.step)}: ${step.label}. ${step.detail}`);
        }
        lines.push("");
      }
      if (finding.ai) {
        lines.push("AI explanation (not a confirmed finding):", "", finding.ai.explanation, "");
      }
    }
  };
  write("Introduced", review.findings);
  write("Pre-existing", review.pre_existing);
  return lines.join("\n");
}

export function downloadReport(review: Review) {
  const blob = new Blob([reportMarkdown(review)], { type: "text/markdown" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `${review.filename.replace(/[^\w.-]+/g, "_") || "review"}.md`;
  link.click();
  URL.revokeObjectURL(url);
}
