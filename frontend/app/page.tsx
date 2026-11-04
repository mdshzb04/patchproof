"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { ChevronRight } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { getJSON, postJSON, type Review, type Stats } from "@/lib/api";
import { queueStatus, when } from "@/lib/format";
import { usePageTitle, useToast } from "@/components/chrome";

export default function OverviewPage() {
  usePageTitle("Overview");
  const router = useRouter();
  const toast = useToast();
  const [stats, setStats] = useState<Stats | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState("");

  const load = useCallback(() => {
    setError("");
    getJSON<Stats>("/api/stats")
      .then(setStats)
      .catch((err: Error) => setError(err.message || "API unreachable"));
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  async function runDemo() {
    setBusy(true);
    setStatus("Running static analysis…");
    try {
      const example = await getJSON<{ filename: string; text: string }>("/api/examples/demo");
      const review = await postJSON<Review>("/api/reviews/text", {
        text: example.text,
        filename: example.filename,
        title: "Demo: backup job patch",
        enrich: false,
      });
      router.push(`/review/${review.id}`);
    } catch (err) {
      const message = err instanceof Error ? err.message : "Demo review failed.";
      setStatus("");
      toast.push(message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="page">
      <p className="eyebrow">Engineering intelligence</p>
      <h1 className="display">Code reviews you can trust.</h1>
      <p className="lede">Find risks in changed code. Inspect the evidence. Ship with confidence.</p>
      <div className="actions">
        <Link href="/new" className="btn primary">New review</Link>
        <button type="button" className={busy ? "btn busy" : "btn"} disabled={busy} onClick={runDemo}>Try the demo diff</button>
        <Link href="/evaluation" className="btn">View evaluation</Link>
      </div>
      {status && <p className="status-line">{status}</p>}

      {error && (
        <p className="note bad">
          {error}. The API on port 8000 did not respond.
          <button type="button" className="btn" style={{ marginLeft: 8 }} onClick={load}>Retry</button>
        </p>
      )}
      {!stats && !error && (
        <div className="metrics" aria-hidden>
          <div className="metric"><span className="skel" /><span className="skel" /></div>
          <div className="metric"><span className="skel" /><span className="skel" /></div>
          <div className="metric"><span className="skel" /><span className="skel" /></div>
          <div className="metric"><span className="skel" /><span className="skel" /></div>
        </div>
      )}

      {stats && (
        <>
          {stats.sample_reviews > 0 && (
            <p className="note">
              {stats.sample_reviews === stats.reviews
                ? "Sample data only. These counts come from the bundled demo reviews, not from traffic."
                : `${stats.sample_reviews} of ${stats.reviews} reviews are bundled samples. Counts include both.`}
            </p>
          )}
          <section className="metrics" aria-label="Review metrics">
            <div className="metric"><span>Total reviews</span><strong>{stats.reviews}</strong></div>
            <div className="metric"><span>Findings detected</span><strong>{stats.findings}</strong></div>
            <div className="metric"><span>Critical & high</span><strong>{stats.critical_high}</strong></div>
            <div className="metric"><span>Resolved</span><strong>{stats.resolved}</strong></div>
          </section>

          <div className="section-head">
            <h2>Recent reviews</h2>
            <Link href="/history">Review history</Link>
          </div>
          <div className="list">
            {stats.recent.length === 0 && (
              <div className="empty">
                <strong>No reviews yet</strong>
                Run the demo diff or upload a change.
                <div className="actions" style={{ justifyContent: "center" }}>
                  <Link href="/new" className="btn primary">New review</Link>
                </div>
              </div>
            )}
            {stats.recent.map((row) => {
              const status = queueStatus(row.findings, row.critical_high);
              return (
                <Link className="row" key={row.id} href={`/review/${row.id}`}>
                  <div>
                    <div className="name">{row.title}</div>
                    <div className="sub">
                      {row.filename}
                      {row.source === "sample" ? " · sample" : ""}
                    </div>
                  </div>
                  <div className="sub hide-sm">{when(row.created_at)}</div>
                  <div className="count hide-sm">{row.findings} <em>new</em></div>
                  <div className="count hide-sm">{row.pre_existing} <em>prior</em></div>
                  <div>
                    {row.critical_high > 0 && <span className="chip high">{row.critical_high} critical/high</span>}
                  </div>
                  <span className="pill">{status}</span>
                  <span className="open-link">Open <ChevronRight size={14} /></span>
                </Link>
              );
            })}
          </div>
        </>
      )}
    </div>
  );
}
