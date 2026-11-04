"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { getJSON } from "@/lib/api";
import { usePageTitle } from "@/components/chrome";

type CaseRow = {
  id: string;
  file: string;
  label: string;
  expect: string[];
  found: string[];
  missed: string[];
  extra: string[];
  pass: boolean;
};

type Report = {
  sample_count: number;
  vulnerable_count: number;
  safe_count: number;
  true_positives: number;
  false_positives: number;
  true_negatives: number;
  false_negatives: number;
  precision: number;
  recall: number;
  f1: number;
  disclaimer: string;
  cases: CaseRow[];
};

export default function EvaluationPage() {
  usePageTitle("Evaluation");
  const [report, setReport] = useState<Report | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    setBusy(true);
    setError("");
    getJSON<Report>("/api/evaluation")
      .then(setReport)
      .catch((err: Error) => setError(err.message))
      .finally(() => setBusy(false));
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const rules = useMemo(() => (report ? perRule(report.cases) : []), [report]);
  const rate = report ? falsePositiveRate(report.false_positives, report.true_negatives) : null;
  const chart = report
    ? [
        { name: "True positives", value: report.true_positives },
        { name: "False positives", value: report.false_positives },
        { name: "True negatives", value: report.true_negatives },
        { name: "False negatives", value: report.false_negatives },
      ]
    : [];
  const peak = Math.max(1, ...chart.map((row) => row.value));

  return (
    <div className="page">
      <p className="eyebrow">Evaluation</p>
      <h1 className="display">Measure the reviewer.</h1>
      <p className="lede">Numbers below are computed by the API on the labelled files. They are not a field score.</p>
      <div className="actions">
        <button type="button" className={busy ? "btn busy" : "btn"} disabled={busy} onClick={load}>
          {busy ? "Running…" : "Re-run evaluation"}
        </button>
      </div>
      {error && (
        <p className="note bad">
          {error}
          <button type="button" className="btn" style={{ marginLeft: 8 }} onClick={load}>Retry</button>
        </p>
      )}
      {!report && !error && (
        <div style={{ marginTop: 20 }}>
          <div className="skel" />
          <div className="skel" />
          <div className="skel" />
        </div>
      )}
      {report && rate && (
        <>
          <section className="metrics five" aria-label="Benchmark metrics">
            <div className="metric"><span>Precision</span><strong>{report.precision.toFixed(3)}</strong></div>
            <div className="metric"><span>Recall</span><strong>{report.recall.toFixed(3)}</strong></div>
            <div className="metric"><span>F1</span><strong>{report.f1.toFixed(3)}</strong></div>
            <div className="metric" title="False positives / (false positives + true negatives), from this response">
              <span>False-positive rate</span>
              <strong>{rate}</strong>
            </div>
            <div className="metric"><span>Sample count</span><strong>{report.sample_count}</strong></div>
          </section>
          <p className="meta" style={{ marginTop: 10 }}>
            {report.sample_count} samples · {report.vulnerable_count} vulnerable · {report.safe_count} safe · AST rules only
          </p>

          <div className="section-head"><h2>Counts from this run</h2></div>
          <div className="bars">
            {chart.map((row) => (
              <div className="bar-row" key={row.name}>
                <span>{row.name}</span>
                <span className="track"><span style={{ width: `${(row.value / peak) * 100}%` }} /></span>
                <span className="mono">{row.value}</span>
              </div>
            ))}
          </div>

          <div className="section-head"><h2>Confusion matrix</h2></div>
          <div className="matrix">
            <div className="mh" />
            <div className="mh">Predicted risk</div>
            <div className="mh">Predicted safe</div>
            <div className="mh">Actual risk</div>
            <div><span className="meta">True positive</span><strong>{report.true_positives}</strong></div>
            <div><span className="meta">False negative</span><strong>{report.false_negatives}</strong></div>
            <div className="mh">Actual safe</div>
            <div><span className="meta">False positive</span><strong>{report.false_positives}</strong></div>
            <div><span className="meta">True negative</span><strong>{report.true_negatives}</strong></div>
          </div>

          <div className="section-head"><h2>Per rule</h2></div>
          <table className="table">
            <thead>
              <tr><th>Rule</th><th>True positive</th><th>False negative</th><th>Extra hits</th></tr>
            </thead>
            <tbody>
              {rules.map((row) => (
                <tr key={row.rule}>
                  <td className="mono">{row.rule}</td>
                  <td className="mono">{row.tp}</td>
                  <td className="mono">{row.fn}</td>
                  <td className="mono">{row.fp}</td>
                </tr>
              ))}
            </tbody>
          </table>

          <div className="section-head"><h2>Dataset</h2></div>
          <p className="lede">
            {report.vulnerable_count} files are labelled with the rule that should fire. {report.safe_count} files are the safe twin of each rule. The case table lists every file the API scored.
          </p>
          <table className="table">
            <thead>
              <tr><th>Case</th><th>Expect</th><th>Found</th><th>Result</th></tr>
            </thead>
            <tbody>
              {report.cases.map((row) => (
                <tr key={row.id}>
                  <td>
                    <div>{row.id}</div>
                    <div className="sub">{row.file}</div>
                  </td>
                  <td className="mono">{row.expect.join(", ") || "—"}</td>
                  <td className="mono">{row.found.join(", ") || "—"}</td>
                  <td className={row.pass ? "pass" : "fail"}>{row.pass ? "pass" : "fail"}</td>
                </tr>
              ))}
            </tbody>
          </table>

          <div className="section-head"><h2>Methodology</h2></div>
          <p className="lede">
            A vulnerable sample lists rule ids that must fire. Each expected rule that fires is a true positive. Each expected rule that does not fire is a false negative. A rule that fires but was not expected is a false positive. A safe sample with no findings is one true negative. Precision, recall, and F1 are calculated from those counts in the API response. Bandit is not part of this score.
          </p>

          <div className="section-head"><h2>Limitations</h2></div>
          <p className="lede">{report.disclaimer}</p>
        </>
      )}
    </div>
  );
}

function falsePositiveRate(fp: number, tn: number) {
  if (fp + tn === 0) return "—";
  return (fp / (fp + tn)).toFixed(3);
}

function perRule(cases: CaseRow[]) {
  const ids = new Set<string>();
  for (const row of cases) {
    row.expect.forEach((id) => ids.add(id));
    row.found.forEach((id) => ids.add(id));
  }
  return [...ids].sort().map((rule) => {
    let tp = 0;
    let fn = 0;
    let fp = 0;
    for (const row of cases) {
      const expected = row.expect.includes(rule);
      const found = row.found.includes(rule);
      if (expected && found) tp += 1;
      else if (expected && !found) fn += 1;
      else if (!expected && found) fp += 1;
    }
    return { rule, tp, fn, fp };
  });
}
