"use client";

import { useRouter } from "next/navigation";
import { Upload } from "lucide-react";
import { useState } from "react";
import { API, getJSON, postJSON, type Review } from "@/lib/api";
import { usePageTitle, useToast } from "@/components/chrome";

const LIMIT = "1 MB per file. A zip may hold 40 Python files, up to 2 MB expanded.";

export default function NewReviewPage() {
  usePageTitle("New review");
  const router = useRouter();
  const toast = useToast();
  const [text, setText] = useState("");
  const [filename, setFilename] = useState("paste.diff");
  const [file, setFile] = useState<File | null>(null);
  const [enrich, setEnrich] = useState(false);
  const [over, setOver] = useState(false);
  const [status, setStatus] = useState("");
  const [progress, setProgress] = useState<number | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  function takeFile(next: File | null) {
    if (!next) return;
    const allowed = /\.(diff|patch|py|zip)$/i.test(next.name);
    if (!allowed) {
      setFile(null);
      setError("Use a .diff, .patch, .py, or .zip file.");
      return;
    }
    if (next.size === 0) {
      setFile(null);
      setError("That file is empty.");
      return;
    }
    if (next.size > 1_000_000) {
      setFile(null);
      setError("That file is larger than 1 MB.");
      return;
    }
    setError("");
    setFile(next);
    setStatus(`${next.name} selected. Run the review when ready.`);
  }

  async function loadExample(path: string) {
    setError("");
    setFile(null);
    setStatus("Loading example…");
    try {
      const example = await getJSON<{ filename: string; text: string }>(path);
      setText(example.text);
      setFilename(example.filename);
      setStatus(`Loaded ${example.filename}.`);
    } catch (err) {
      setStatus("");
      setError(err instanceof Error ? err.message : "Could not load the example.");
    }
  }

  async function runDemo() {
    setBusy(true);
    setError("");
    setStatus("Loading the demo diff…");
    try {
      const example = await getJSON<{ filename: string; text: string }>("/api/examples/demo");
      setText(example.text);
      setFilename(example.filename);
      setFile(null);
      setStatus("Running static analysis…");
      const review = await postJSON<Review>("/api/reviews/text", {
        text: example.text,
        filename: example.filename,
        title: "Demo: backup job patch",
        enrich,
      });
      toast.push("Review ready");
      router.push(`/review/${review.id}`);
    } catch (err) {
      const message = err instanceof Error ? err.message : "Demo review failed.";
      setError(message);
      setStatus("");
      toast.push(message);
    } finally {
      setBusy(false);
    }
  }

  async function runText() {
    setBusy(true);
    setError("");
    setStatus("Parsing the diff and running static analysis…");
    try {
      const review = await postJSON<Review>("/api/reviews/text", {
        text,
        filename,
        title: filename,
        enrich,
      });
      toast.push("Review ready");
      router.push(`/review/${review.id}`);
    } catch (err) {
      const message = err instanceof Error ? err.message : "Review failed.";
      setError(message);
      setStatus("");
      toast.push(message);
    } finally {
      setBusy(false);
    }
  }

  function runFile(target: File) {
    setBusy(true);
    setError("");
    setProgress(0);
    setStatus(`Uploading ${target.name}…`);
    const body = new FormData();
    body.set("file", target);
    body.set("enrich", enrich ? "true" : "false");
    body.set("title", target.name);
    const xhr = new XMLHttpRequest();
    xhr.open("POST", `${API}/api/reviews`);
    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable) setProgress(Math.round((event.loaded / event.total) * 100));
    };
    xhr.onload = () => {
      setProgress(null);
      let payload: { detail?: string; id?: string } = {};
      try {
        payload = JSON.parse(xhr.responseText);
      } catch {
        payload = {};
      }
      if (xhr.status >= 200 && xhr.status < 300 && payload.id) {
        toast.push("Review ready");
        router.push(`/review/${payload.id}`);
        return;
      }
      const message = payload.detail || "Upload rejected.";
      setError(message);
      setStatus("");
      setBusy(false);
      toast.push(message);
    };
    xhr.onerror = () => {
      setBusy(false);
      setProgress(null);
      setError("Upload failed.");
      setStatus("");
    };
    xhr.send(body);
  }

  return (
    <div className="page">
      <p className="eyebrow">New review</p>
      <h1 className="display">Start a code review.</h1>
      <p className="lede">Analyse a code change and understand the risks before it reaches production.</p>

      <div
        className={over ? "drop over" : "drop"}
        onDragOver={(event) => {
          event.preventDefault();
          setOver(true);
        }}
        onDragLeave={() => setOver(false)}
        onDrop={(event) => {
          event.preventDefault();
          setOver(false);
          takeFile(event.dataTransfer.files?.[0] || null);
        }}
      >
        <div className="drop-icon" aria-hidden><Upload size={18} /></div>
        <h2>Drop a diff, patch, .py or .zip</h2>
        <p>{LIMIT} The engine does not run the code.</p>
        <div className="kinds" aria-label="Accepted types">
          <span className="chip">.diff</span>
          <span className="chip">.patch</span>
          <span className="chip">.py</span>
          <span className="chip">.zip</span>
        </div>
        <div className="actions">
          <label className="btn primary">
            Choose file
            <input
              className="sr-only"
              type="file"
              accept=".diff,.patch,.py,.zip,text/plain"
              onChange={(event) => takeFile(event.target.files?.[0] || null)}
            />
          </label>
          <button type="button" className={busy ? "btn busy" : "btn"} disabled={busy} onClick={runDemo}>Try the demo diff</button>
          <button type="button" className="btn" disabled={busy} onClick={() => loadExample("/api/examples/safe-fix")}>Load safe fix</button>
        </div>
        {file && (
          <div className="file-chip">
            <span>{file.name}</span>
            <span>{Math.ceil(file.size / 1024)} KB</span>
          </div>
        )}
        {progress !== null && (
          <div className="progress" aria-valuenow={progress} aria-valuemin={0} aria-valuemax={100}>
            <span style={{ width: `${progress}%` }} />
          </div>
        )}
      </div>

      <label className="field-label" htmlFor="diff">Or paste a unified diff</label>
      <textarea
        id="diff"
        className="editor"
        value={text}
        spellCheck={false}
        onChange={(event) => {
          setText(event.target.value);
          setFilename("paste.diff");
        }}
        placeholder={"--- a/app.py\n+++ b/app.py\n@@ ..."}
      />

      <label className="check">
        <input type="checkbox" checked={enrich} onChange={(event) => setEnrich(event.target.checked)} />
        <span>Ask the model to explain confirmed findings. Static results still stand if the model is unavailable.</span>
      </label>

      <div className="actions">
        <button
          type="button"
          className={busy ? "btn primary busy" : "btn primary"}
          disabled={busy || (!file && !text.trim())}
          onClick={() => (file ? runFile(file) : runText())}
        >
          {busy ? "Running…" : file ? "Review file" : "Review pasted diff"}
        </button>
      </div>
      {status && <p className="status-line">{status}</p>}
      {error && <p className="note bad">{error}</p>}
    </div>
  );
}
