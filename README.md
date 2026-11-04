# PatchProof

PatchProof reviews a **code change**, not a whole repository. A developer uploads a Git diff. The engine parses the hunks, runs deterministic Python checks on the new file, and keeps a finding only when the matched lines were added or modified. Every finding carries the line, the rule, the matched code, the impact, and a fix. That chain is the product.

Generic review bots fail this job in two ways. They scan unchanged code and call it a new bug, and they let a model invent a vulnerability the diff does not support. PatchProof separates four things:

- Confirmed static-analysis findings
- Findings that still need investigation
- Pre-existing issues that the diff did not touch
- Optional model explanations, which never change the rule result

This is a hackathon build for Neural Storm 2026, track FT-05. It is not a production scanner and it does not claim coverage of real-world repositories.

## Architecture

```
diff / .py / .zip
        │
        ▼
  diff parser  ── changed line numbers
        │
        ▼
  AST rules (PP001–PP010)  +  Bandit, same line, same rule, merged
        │
        ▼
  change filter  ── introduced vs pre-existing
        │
        ▼
  optional OpenAI-compatible explanation
        │
        ▼
  JSON review  ── Next.js results, evidence chain, evaluation
```

| Piece | Choice |
| --- | --- |
| API | FastAPI, Pydantic, JSON file under `backend/data/` |
| Analysis | Python `ast`, unified-diff parser, Bandit as a subprocess |
| UI | Next.js 15, TypeScript, Tailwind, Inter, JetBrains Mono |
| AI | `POST /chat/completions` when `OPENAI_API_KEY` is set |

No Docker, database, authentication, or payment. Uploaded code is parsed, never imported or executed. Dependencies inside an upload are not installed.

## Detection pipeline

Rules:

| ID | What it matches |
| --- | --- |
| PP001 | `shell=True` or `os.system` / `os.popen`. Critical when the command is not a constant. |
| PP002 | `eval` / `exec` (not `ast.literal_eval`) |
| PP003 | `pickle.load` / `pickle.loads` |
| PP004 | `yaml.load` without `SafeLoader`, plus `unsafe_load` / `full_load` |
| PP005 | Live-looking key prefixes, or a secret-shaped name assigned a literal |
| PP006 | `verify=False`, `CERT_NONE`, unverified SSL context |
| PP007 | `tempfile.mktemp` |
| PP008 | MD5 / SHA-1, unless `usedforsecurity=False`, and `MODE_ECB` |
| PP009 | `execute` with an f-string, `%`, concatenation, or `.format` |
| PP010 | `except Exception` / bare `except` whose body only passes, continues, or returns |

A finding on an unchanged line is stored as pre-existing and hidden until the reviewer asks for it. A safe edit in the same patch, such as `utils/labels.py` in the demo, produces no finding.

Partial diffs that omit surrounding lines are scanned on the added lines only. Those results say the file was not reconstructed. Complete modules reconstructed from a full-context diff go through the AST, then Bandit. If both report the same rule within three lines, PatchProof keeps one finding and records the Bandit test id.

## Evidence chain

Each finding renders five steps from the analysis record:

1. Changed line
2. Rule id
3. Matched code
4. Impact
5. Suggested fix

The model panel, when present, sits under a dashed border and is labelled as an explanation, not a confirmation. With no API key the panel says enrichment is unavailable and the static findings remain.

## Evaluation

`GET /api/evaluation` runs the AST rules on `backend/benchmark/`. The set is 10 vulnerable files and 10 safe twins, one pair per rule. A vulnerable file scores a true positive per expected rule that fired, a false negative per expected rule that did not, and a false positive per extra rule. A safe file with no findings is one true negative. A safe file with findings adds one false positive per rule.

Latest run of `backend/.venv/bin/pytest -q` (14 tests) and the benchmark helper:

| Metric | Value |
| --- | --- |
| Samples | 20 |
| True positives | 10 |
| False positives | 0 |
| True negatives | 10 |
| False negatives | 0 |
| Precision | 1.0 |
| Recall | 1.0 |
| F1 | 1.0 |

That score means the rules match this labelled set. It is not a claim about GitHub, other languages, or novel bugs. Bandit is not part of the score, so a Bandit-only hit cannot inflate it. Re-run the page or `GET /api/evaluation` rather than trusting a copied number if the rules change.

## Demo

The bundled patch is `backend/examples/demo_pr.diff`, generated from `examples/before` and `examples/after`.

Introduced in `service/jobs.py`:

- PP001 shell command built with an f-string
- PP003 `pickle.loads`
- PP006 `verify=False`

Left on context lines, so they are pre-existing, not new:

- PP002 `eval`
- PP005 `BACKUP_TOKEN`

`utils/labels.py` only changes a slug helper. It is in the diff and it is clean.

`backend/examples/safe_fix.diff` replaces the shell call, pickle, and `verify=False`. Introduced findings on that patch are empty. The untouched `eval` and token stay pre-existing.

Walkthrough: [DEMO.md](DEMO.md). Ninety-second judge script: [DEMO_SCRIPT.md](DEMO_SCRIPT.md). Uploadable files: `sample/`. Screenshots from a live run: `screenshots/`.

## Setup

Python 3.12 and Node 24 were used. Python 3.11+ is the intended floor.

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pytest
uvicorn app.main:app --port 8000
```

Second terminal:

```bash
cd frontend
npm install
npm run dev
```

Open http://127.0.0.1:3000. The API is http://127.0.0.1:8000. On startup the API writes two sample reviews into `backend/data/reviews.json` if that file is empty. The UI marks them as sample data.

Optional model explanations, from the repo root or the shell that starts the API:

```bash
export OPENAI_API_KEY=...
export OPENAI_BASE_URL=https://api.openai.com/v1   # any compatible base
export OPENAI_MODEL=gpt-4o-mini
```

Copy `.env.example` to `backend/.env`. The API reads that file at startup and does not print the key. Leave the key unset and reviews still complete. Static findings do not change when the model is off.

`make test`, `make api`, and `make web` wrap the same commands after the venv and `npm install` exist.

## API

| Method | Path | Role |
| --- | --- | --- |
| GET | `/api/health` | Process up, key present or not |
| GET | `/api/stats` | Counts from stored reviews |
| GET | `/api/reviews` | Stored reviews |
| GET | `/api/reviews/{id}` | Findings, files, stages, summary |
| POST | `/api/reviews/text` | JSON body `{text, filename, title, enrich}` |
| POST | `/api/reviews` | Multipart `.diff`, `.patch`, `.py`, or `.zip` |
| POST | `/api/reviews/{id}/findings/{fid}/resolve` | `{resolved: true}` |
| GET | `/api/examples/demo` | Demo diff text |
| GET | `/api/examples/safe-fix` | Fixed diff text |
| GET | `/api/evaluation` | Live benchmark numbers |

Uploads over 1 MB are rejected. Zip entries with `..` or absolute paths are rejected. Non-Python files inside a zip are ignored. The expanded Python total is capped at 2 MB and 40 files.

## Tests

```bash
cd backend && .venv/bin/pytest -q
```

Covered: hunk line numbers, gapped diffs, unsafe diff paths, multiline calls attributed to the added line, each rule and its safe twin, metric arithmetic, SQL format variants, dedupe, the demo filter, the safe fix, zip path traversal, binary rejection, AI timeout fallback, and the upload API.

Result of the run during this build: **14 passed**.

## Limitations

- Python only. Other languages in a diff are skipped.
- No cross-function taint tracking. A constant `shell=True` is "needs investigation", not a confirmed injection.
- A partial hunk is weaker than a full file. Line patterns can miss a risk that spans lines, and they can miss context.
- Secret detection is a prefix and name check. It will miss novel formats and can flag realistic fixtures.
- The benchmark is 20 hand-written files. Perfect precision here does not transfer.
- Bandit findings outside the mapped test ids are dropped on purpose, to avoid import-blacklist noise.
- Reviews sit in a JSON file on one machine. There is no auth.
- The model is asked not to invent CVEs. The prompt is not a guarantee. Read the static evidence.
- The UI does not run a second analysis when you mark a finding resolved. Resolved is a reviewer flag.

## Future work

Richer diffs against a real git checkout, so unchanged lines outside the hunk are still visible without being called new. More languages. A reviewer-supplied allowlist. A larger benchmark with third-party diffs, scored the same way, published with the failures.

## AI-tool disclosure

The application was implemented with Cursor, using Grok 4.7 as the coding assistant. At runtime, PatchProof calls an OpenAI-compatible chat API only when `OPENAI_API_KEY` is set and the reviewer opts in. That call explains confirmed findings. It does not decide them.
