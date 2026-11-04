# 90-second demo

Open http://127.0.0.1:3000. API on port 8000. Leave AI off for the first pass so the static result is the whole story.

1. Overview. Say: "This reviews the diff, not the repository. Sample rows stay labelled Sample."
2. Click **Try the demo diff**. The status line says static analysis is running. The review opens on the first finding.
3. Point at the highlighted line in `service/jobs.py`: `subprocess.run(... shell=True)`. Say the chain: changed line, rule PP001, matched code, impact, fix.
4. Press J. The next row is pickle. Press J again. TLS `verify=False`. Those three are new. Eval and the token are pre-existing; they stay hidden until that filter is on.
5. Click **Copy suggested fix**. It copies the list-form `subprocess.run` from the finding, not a made-up patch.
6. Click **Export report**. Open the Markdown. It has the summary, the three introduced findings, the evidence, and the fixes.
7. If there is time, open Evaluation. The numbers are from `GET /api/evaluation` on the 20 labelled files. Read the limitations line out loud.

Expected introduced findings on the demo diff:

- PP001 shell command, `service/jobs.py`
- PP003 `pickle.loads`
- PP006 `verify=False`

`utils/labels.py` is in the diff and has no finding.

To upload instead of the demo, use `sample/jobs.py`, `sample/debug.py`, or `sample/query.py`. Those are whole-file snapshots, so every line is in scope and the banner says so. They should raise PP001, PP002, and PP009 plus PP005.
