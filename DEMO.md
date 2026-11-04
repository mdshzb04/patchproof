# Demo script

About 4 minutes. No code edits. API on port 8000, UI on port 3000. Leave `OPENAI_API_KEY` unset for the first pass so the static result is obvious. Turn it on only if you want the dashed explanation panel.

1. Open http://127.0.0.1:3000.
   The queue shows two sample reviews. The banner says the counts are sample data.

2. Open **Sample: backup job patch**.
   Introduced findings are PP001, PP003, and PP006. Stages show real parse, AST, and Bandit times.

3. Select the shell finding.
   The evidence chain reads: changed line, rule PP001, the f-string plus `shell=True`, impact, fix as an argument list.
   The code pane marks `+` on changed lines and highlights the finding line.
   The AI box says there is no model note. That is expected without a key.

4. Enable the **pre-existing** filter.
   `eval` (PP002) and `BACKUP_TOKEN` (PP005) appear. They sit on context lines. They are not in the introduced count.

5. Switch the file to `utils/labels.py`.
   The slug change is in the diff. No finding points at it.

6. New review → **Load safe fix** → **Run review**.
   Introduced findings: none.
   Pre-existing still lists `eval` and the token, because that patch does not touch them.

7. Open **Evaluation**.
   The page runs the 20-file benchmark and prints precision, recall, and F1 from that run. Read the disclaimer out loud: this is a controlled set, not a field measurement.

If a key is configured, repeat step 3 with the AI checkbox on. The static severity and evidence stay. The dashed panel is the only place model text appears.
