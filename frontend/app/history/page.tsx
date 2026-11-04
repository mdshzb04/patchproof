"use client";

import Link from "next/link";
import { ChevronRight } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { getJSON, type Review } from "@/lib/api";
import { reviewStatus, when } from "@/lib/format";
import { usePageTitle } from "@/components/chrome";

export default function HistoryPage() {
  usePageTitle("History");
  const [reviews, setReviews] = useState<Review[] | null>(null);
  const [error, setError] = useState("");
  const [query, setQuery] = useState("");

  const load = useCallback(() => {
    setError("");
    getJSON<Review[]>("/api/reviews")
      .then(setReviews)
      .catch((err: Error) => setError(err.message));
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const rows = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (!reviews) return [];
    if (!needle) return reviews;
    return reviews.filter((review) =>
      `${review.title} ${review.filename}`.toLowerCase().includes(needle),
    );
  }, [reviews, query]);

  return (
    <div className="page">
      <p className="eyebrow">History</p>
      <h1 className="display">Every review on this machine.</h1>
      <p className="lede">Stored locally by the API. Sample reviews stay labelled.</p>
      <label className="field-label" htmlFor="filter">Filter</label>
      <input
        id="filter"
        className="editor"
        style={{ minHeight: 0, height: 40 }}
        value={query}
        onChange={(event) => setQuery(event.target.value)}
        placeholder="Title or filename"
      />
      {error && (
        <p className="note bad">
          {error}
          <button type="button" className="btn" style={{ marginLeft: 8 }} onClick={load}>Retry</button>
        </p>
      )}
      {!reviews && !error && <div className="skel" style={{ marginTop: 16 }} />}
      {reviews && (
        <div className="list" style={{ marginTop: 16 }}>
          {rows.length === 0 && (
            <div className="empty">
              <strong>{reviews.length === 0 ? "No reviews yet" : "No reviews match"}</strong>
              {reviews.length === 0 ? "Start with a diff." : "Try another name."}
            </div>
          )}
          {rows.map((review) => {
            const status = reviewStatus(review);
            const high = review.findings.filter((item) => !item.resolved && (item.severity === "critical" || item.severity === "high")).length;
            return (
              <Link className="row" key={review.id} href={`/review/${review.id}`}>
                <div>
                  <div className="name">{review.title}</div>
                  <div className="sub">
                    {review.filename}
                    {review.source === "sample" ? " · sample" : ""}
                  </div>
                </div>
                <div className="sub hide-sm">{when(review.created_at)}</div>
                <div className="count hide-sm">{review.findings.length} <em>new</em></div>
                <div className="count hide-sm">{review.pre_existing.length} <em>prior</em></div>
                <div>
                  {high > 0 && <span className="chip high">{high} critical/high</span>}
                </div>
                <span className="pill">{status}</span>
                <span className="open-link">Open <ChevronRight size={14} /></span>
              </Link>
            );
          })}
        </div>
      )}
    </div>
  );
}
