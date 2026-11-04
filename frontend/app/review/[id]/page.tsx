"use client";

import { useParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { getJSON, postJSON, type EvidenceStep, type Finding, type Review } from "@/lib/api";
import { usePageTitle, useToast } from "@/components/chrome";
import { LineText } from "@/lib/highlight";
import { downloadReport, reviewStatus, stepName, when } from "@/lib/format";

const SEVERITIES = ["critical", "high", "medium", "low"] as const;
const CATEGORIES = ["security", "reliability"] as const;

type Row = Finding & { prior: boolean };

export default function ReviewPage() {
  const params = useParams<{ id: string }>();
  const toast = useToast();
  const [review, setReview] = useState<Review | null>(null);
  const [error, setError] = useState("");
  const [selected, setSelected] = useState("");
  const [showPrior, setShowPrior] = useState(false);
  const [filePath, setFilePath] = useState("");
  const [severity, setSeverity] = useState<Record<string, boolean>>({ critical: true, high: true, medium: true, low: true });
  const [category, setCategory] = useState<Record<string, boolean>>({ security: true, reliability: true });
  const [origin, setOrigin] = useState<Record<string, boolean>>({ confirmed: true, needs_investigation: true });

  usePageTitle(review?.title || "Review");

  useEffect(() => {
    getJSON<Review>(`/api/reviews/${params.id}`)
      .then((data) => {
        setReview(data);
        const first = data.findings[0] || data.pre_existing[0];
        setSelected(first?.id || "");
        setFilePath(first?.file || data.files[0]?.path || "");
        if (!data.findings.length && data.pre_existing.length) setShowPrior(true);
      })
      .catch((err: Error) => setError(err.message));
  }, [params.id]);

  const rows = useMemo(() => {
    if (!review) return [];
    const pool: Row[] = [
      ...review.findings.map((item) => ({ ...item, prior: false })),
      ...(showPrior ? review.pre_existing.map((item) => ({ ...item, prior: true })) : []),
    ];
    return pool.filter((item) => severity[item.severity] && category[item.category] && origin[item.origin]);
  }, [review, showPrior, severity, category, origin]);

  const finding = rows.find((item) => item.id === selected) ?? null;

  useEffect(() => {
    if (finding?.file) setFilePath(finding.file);
  }, [finding?.id, finding?.file]);

  const file = review?.files.find((item) => item.path === filePath) || review?.files[0];

  useEffect(() => {
    if (!finding || !file || file.path !== finding.file) return;
    const pane = document.querySelector(".codepane");
    const line = document.getElementById(`ln-${finding.line}`);
    if (!pane || !line || !(pane instanceof HTMLElement)) return;
    const paneTop = pane.getBoundingClientRect().top;
    const lineTop = line.getBoundingClientRect().top;
    pane.scrollTo({ top: pane.scrollTop + (lineTop - paneTop) - pane.clientHeight / 2, behavior: "smooth" });
  }, [finding, file]);

  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      const target = event.target as HTMLElement | null;
      const typing = target && (target.tagName === "INPUT" || target.tagName === "TEXTAREA" || target.isContentEditable);
      if (typing || event.metaKey || event.ctrlKey || event.altKey) return;
      if (event.key === "Escape") {
        setSelected("");
        return;
      }
      if (event.key !== "j" && event.key !== "k") return;
      event.preventDefault();
      const ids = rows.map((item) => item.id);
      if (!ids.length) return;
      const index = ids.indexOf(selected);
      const next = event.key === "j"
        ? ids[Math.min(ids.length - 1, index < 0 ? 0 : index + 1)]
        : ids[Math.max(0, index <= 0 ? 0 : index - 1)];
      setSelected(next);
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [rows, selected]);

  function clearFilters() {
    setSeverity({ critical: true, high: true, medium: true, low: true });
    setCategory({ security: true, reliability: true });
    setOrigin({ confirmed: true, needs_investigation: true });
    setShowPrior(false);
  }

  async function copyFix(item: Row) {
    try {
      await navigator.clipboard.writeText(item.fix_example);
      toast.push("Suggested fix copied");
    } catch {
      toast.push("Could not copy the fix");
    }
  }

  async function toggleResolved(item: Row) {
    if (!review || item.prior) return;
    try {
      const next = await postJSON<Review>(`/api/reviews/${review.id}/findings/${item.id}/resolve`, {
        resolved: !item.resolved,
      });
      setReview(next);
      toast.push(item.resolved ? "Finding reopened" : "Marked resolved");
    } catch (err) {
      toast.push(err instanceof Error ? err.message : "Could not update the finding");
    }
  }

  if (error) {
    return (
      <div className="page">
        <p className="note bad">{error}</p>
        <button type="button" className="btn" onClick={() => window.location.reload()}>Retry</button>
      </div>
    );
  }
  if (!review) {
    return (
      <div className="review-page">
        <div className="review-head">
          <div className="skel" />
          <div className="skel" style={{ width: "40%", marginTop: 10 }} />
        </div>
      </div>
    );
  }

  const counts = review.summary?.by_severity || { critical: 0, high: 0, medium: 0, low: 0 };
  const status = reviewStatus(review);

  return (
    <div className="review-page">
      <header className="review-head">
        <div className="review-head-row">
          <div>
            <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
              <span className="pill">{status}</span>
              {review.source === "sample" && <span className="pill sample">Sample</span>}
              <span className="pill">{review.mode === "diff" ? "Diff" : "Snapshot"}</span>
            </div>
            <h1>{review.title}</h1>
            <p className="meta">
              <span className="mono">{review.filename}</span>
              {" · "}
              {when(review.created_at)}
            </p>
          </div>
          <button
            type="button"
            className="btn"
            onClick={() => {
              downloadReport(review);
              toast.push("Report downloaded");
            }}
          >
            Export report
          </button>
        </div>
        <div className="summary">
          <span><span className="label">Critical</span><b className="sev critical">{counts.critical || 0}</b></span>
          <span><span className="label">High</span><b className="sev high">{counts.high || 0}</b></span>
          <span><span className="label">Medium</span><b className="sev medium">{counts.medium || 0}</b></span>
          <span><span className="label">Low</span><b className="sev low">{counts.low || 0}</b></span>
          <span><span className="label">New</span><b>{review.findings.length}</b></span>
          <span><span className="label">Pre-existing</span><b>{review.pre_existing.length}</b></span>
        </div>
        {review.ai_status !== "ok" && <p className="meta">{review.ai_message}</p>}
        {review.stages.length > 0 && (
          <ol className="stages">
            {review.stages.map((stage) => (
              <li key={stage.name}>
                <span>{stage.name}</span>
                <span className="mono">{stage.status} · {stage.ms} ms</span>
              </li>
            ))}
          </ol>
        )}
      </header>

      <div className={review.findings.length + review.pre_existing.length === 0 ? "review-grid solo" : "review-grid"}>
        <aside className="explorer" aria-label="Findings">
          <div className="filters">
            {SEVERITIES.map((name) => (
              <Filter key={name} on={severity[name]} label={name} onClick={() => setSeverity({ ...severity, [name]: !severity[name] })} />
            ))}
            {CATEGORIES.map((name) => (
              <Filter key={name} on={category[name]} label={name} onClick={() => setCategory({ ...category, [name]: !category[name] })} />
            ))}
            <Filter on={origin.confirmed} label="confirmed" onClick={() => setOrigin({ ...origin, confirmed: !origin.confirmed })} />
            <Filter on={origin.needs_investigation} label="investigate" onClick={() => setOrigin({ ...origin, needs_investigation: !origin.needs_investigation })} />
            <Filter on={showPrior} label={`pre-existing ${review.pre_existing.length}`} onClick={() => setShowPrior(!showPrior)} />
          </div>
          <p className="keyhint" title="J next finding, K previous finding, Esc deselect">J next · K previous · Esc clear</p>
          {rows.length === 0 && review.findings.length + review.pre_existing.length > 0 && (
            <div className="finder-empty">
              No findings match these filters.
              <div>
                <button type="button" className="btn" style={{ marginTop: 8 }} onClick={clearFilters}>Clear filters</button>
              </div>
            </div>
          )}
          {rows.map((item) => (
            <button
              key={item.id}
              type="button"
              className={finding?.id === item.id ? "finding active" : "finding"}
              onClick={() => setSelected(item.id)}
            >
              <span className={`chip ${item.severity}`}>{item.severity}</span>
              <p className="title">{item.title}</p>
              <p className="loc">{item.file}:{item.line} · {item.confidence}{item.resolved ? " · resolved" : ""}</p>
              <div className="tags">
                <span className={item.prior ? "chip prior" : "chip new"}>{item.prior ? "Pre-existing" : "New"}</span>
              </div>
            </button>
          ))}
        </aside>

        <section className="code-wrap" aria-label="Changed code">
          <div className="filetabs" role="tablist">
            {review.files.map((item) => (
              <button
                key={item.path}
                type="button"
                role="tab"
                aria-selected={file?.path === item.path}
                onClick={() => setFilePath(item.path)}
              >
                {item.path}
              </button>
            ))}
          </div>
          {review.mode === "snapshot" && (
            <p className="snapshot">Snapshot: whole file reviewed as new code.</p>
          )}
          {review.findings.length + review.pre_existing.length === 0 && (
            <p className="snapshot">No issues detected by static analysis. {review.rules_checked ?? 0} rules checked.</p>
          )}
          {file?.skipped_reason && <p className="meta" style={{ padding: "8px 12px" }}>{file.skipped_reason}</p>}
          <div className="codepane">
            {file && (
              <CodeView
                content={file.content}
                added={review.mode === "snapshot" ? [] : file.added_lines}
                focus={file.path === finding?.file ? finding.line : undefined}
                snapshot={review.mode === "snapshot"}
              />
            )}
          </div>
        </section>

        <aside className="detail" aria-label="Finding detail">
          {!finding && <p className="finder-empty">Select a finding to see why it was raised.</p>}
          {finding && (
            <>
              <p className={`sev ${finding.severity}`}>{finding.severity} severity</p>
              <h2>{finding.title}</h2>
              <p className="meta">
                <span className="mono">{finding.file}:{finding.line}</span>
                {" · "}
                {finding.rule_id}
                {" · confidence "}
                {finding.confidence}
                {finding.bandit_id ? ` · ${finding.bandit_id}` : ""}
              </p>
              <div className="badges">
                {finding.origin === "confirmed" ? (
                  <span className="badge confirmed">Confirmed by static analysis</span>
                ) : (
                  <span className="badge investigate">Needs investigation</span>
                )}
                {finding.ai && <span className="badge ai">AI-enriched explanation</span>}
              </div>
              {!finding.prior && (
                <button type="button" className="btn" style={{ marginTop: 12 }} onClick={() => toggleResolved(finding)}>
                  {finding.resolved ? "Reopen" : "Mark resolved"}
                </button>
              )}

              <Evidence steps={finding.evidence_chain} />

              <section className="block">
                <h3>What was detected</h3>
                <p>{finding.evidence}</p>
              </section>
              <section className="block">
                <h3>Why it matters</h3>
                <p>{finding.impact}</p>
              </section>
              <section className="block">
                <h3>Impact</h3>
                <p>{finding.severity} {finding.category} finding{finding.bandit_id ? `. Bandit ${finding.bandit_id} matched the same pattern.` : "."}</p>
              </section>
              <section className="block">
                <h3>Evidence from the code</h3>
                <pre className="snippet"><LineText text={finding.snippet || " "} /></pre>
              </section>
              <section className="block">
                <h3>Recommended fix</h3>
                <p>{finding.recommendation}</p>
                <div className="compare" style={{ marginTop: 8 }}>
                  <div>
                    <h3>Current</h3>
                    <pre className="snippet"><LineText text={finding.snippet || " "} /></pre>
                  </div>
                  <div>
                    <h3>Suggested</h3>
                    <pre className="snippet"><LineText text={finding.fix_example || " "} /></pre>
                  </div>
                </div>
              </section>

              <div className="actions">
                <button type="button" className="btn" onClick={() => copyFix(finding)}>Copy suggested fix</button>
              </div>
              <div className="ai-box">
                <h3>AI explanation · not a confirmed finding</h3>
                {finding.ai ? (
                  <>
                    <p>{finding.ai.explanation}</p>
                    <p>{finding.ai.why_risky}</p>
                    <p>{finding.ai.scenario}</p>
                    <p>{finding.ai.recommended_fix}</p>
                    {finding.ai.corrected_code && <pre className="snippet"><LineText text={finding.ai.corrected_code} /></pre>}
                    <p className="quiet">Model {finding.ai.model}. This note does not change the rule result.</p>
                  </>
                ) : (
                  <p className="quiet">
                    {review.ai_message.includes("OPENAI_API_KEY") ? "AI enrichment not configured. " : ""}
                    {review.ai_message || "No model note on this finding. The rule evidence above is the record."}
                  </p>
                )}
              </div>

              <details className="fold">
                <summary>How this review was run</summary>
                {review.stages.map((stage) => (
                  <p key={stage.name}>{stage.name} · {stage.ms} ms · {stage.status}. {stage.detail}</p>
                ))}
                {review.notes.map((note) => <p key={note}>{note}</p>)}
              </details>
            </>
          )}
        </aside>
      </div>
    </div>
  );
}

function Evidence({ steps }: { steps: EvidenceStep[] }) {
  if (!steps.length) return null;
  return (
    <section className="proof-wrap" aria-label="Why this finding exists">
      <h3>Why this finding exists</h3>
      <ol className="proof">
        {steps.map((step) => (
          <li key={step.step}>
            <span className="node" aria-hidden />
            <div>
              <p className="step-name">{stepName(step.step)}</p>
              <p className="step-label">{step.label}</p>
              <p className="step-detail">{step.detail}</p>
            </div>
          </li>
        ))}
      </ol>
    </section>
  );
}

function CodeView({ content, added, focus, snapshot }: { content: string; added: number[]; focus?: number; snapshot?: boolean }) {
  const marks = new Set(snapshot ? [] : added);
  return (
    <div>
      {content.split("\n").map((text, index) => {
        const line = index + 1;
        const hot = focus === line;
        return (
          <div key={line} id={`ln-${line}`} className={`codeline${marks.has(line) ? " added" : ""}${hot ? " hot" : ""}`}>
            <span className="ln">{line}</span>
            <span className="gutter">{marks.has(line) ? "+" : ""}</span>
            <span className="src"><LineText text={text.length ? text : " "} /></span>
          </div>
        );
      })}
    </div>
  );
}

function Filter({ on, label, onClick }: { on: boolean; label: string; onClick: () => void }) {
  return (
    <button type="button" className="toggle" aria-pressed={on} onClick={onClick}>
      {label}
    </button>
  );
}
