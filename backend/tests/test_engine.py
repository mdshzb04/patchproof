import difflib
import io
import zipfile

import pytest
from fastapi.testclient import TestClient

from app.diff_parser import DiffParseError, parse_unified_diff
from app.engine import review_diff, review_files
from app.evaluation import load_cases, score_cases
from app.ingest import UploadError, classify
from app.rules import analyze_ast, dedupe, make_finding
from app.samples import demo_diff, safe_fix_diff, write_example_files


def _diff(old: str, new: str, rel: str = "job.py") -> str:
    return "".join(
        difflib.unified_diff(
            old.splitlines(keepends=True),
            new.splitlines(keepends=True),
            fromfile=f"a/{rel}",
            tofile=f"b/{rel}",
            n=10000,
        )
    )


def test_hunk_line_numbers():
    text = "\n".join(
        [
            "--- a/x.py",
            "+++ b/x.py",
            "@@ -1,3 +1,4 @@",
            " a = 1",
            "-b = 2",
            "+b = 3",
            "+c = 4",
            " d = 5",
            "",
        ]
    )
    parsed = parse_unified_diff(text)
    assert parsed[0].path == "x.py"
    assert parsed[0].added_lines == {2, 3}
    assert parsed[0].deleted_lines == {2}
    assert parsed[0].new_content.splitlines() == ["a = 1", "b = 3", "c = 4", "d = 5"]
    assert parsed[0].gaps is False


def test_partial_hunk_is_marked_gapped():
    text = "\n".join(
        [
            "--- a/x.py",
            "+++ b/x.py",
            "@@ -8,3 +8,3 @@",
            " def archive(path):",
            '-    subprocess.run(["tar", path])',
            '+    subprocess.run(f"tar {path}", shell=True)',
            "     return None",
            "",
        ]
    )
    parsed = parse_unified_diff(text)
    assert parsed[0].gaps is True
    assert 9 in parsed[0].added_lines
    review = review_diff(text, title="partial")
    assert any(item.rule_id == "PP001" for item in review.findings)
    assert all(item.file == "x.py" for item in review.findings)


def test_malformed_diff_and_unsafe_path():
    with pytest.raises(DiffParseError):
        parse_unified_diff("not a diff")
    with pytest.raises(DiffParseError):
        parse_unified_diff("--- a/../../etc/passwd\n+++ b/../../etc/passwd\n@@ -0,0 +1 @@\n+x\n")


def test_multiline_call_attributes_to_added_line():
    old = 'import subprocess\n\n\ndef archive(path):\n    subprocess.run(\n        ["tar", path],\n        check=True,\n    )\n'
    new = 'import subprocess\n\n\ndef archive(path):\n    subprocess.run(\n        f"tar {path}",\n        shell=True,\n        check=True,\n    )\n'
    review = review_diff(_diff(old, new), title="multiline")
    shells = [item for item in review.findings if item.rule_id == "PP001"]
    assert len(shells) == 1
    assert shells[0].in_diff is True
    assert shells[0].origin == "confirmed"
    assert "shell=True" in review.files[0].content.splitlines()[shells[0].line - 1] or "tar" in review.files[0].content.splitlines()[shells[0].line - 1]
    assert not any(item.rule_id == "PP001" for item in review.pre_existing)


def test_each_rule_and_safe_twin():
    report = score_cases()
    failed = [row for row in report["cases"] if not row["pass"]]
    assert failed == []
    assert report["sample_count"] == 20
    assert report["true_positives"] == 10
    assert report["false_positives"] == 0
    assert report["false_negatives"] == 0
    assert report["true_negatives"] == 10


def test_metrics_are_derived_from_counts():
    report = score_cases()
    tp, fp, fn = report["true_positives"], report["false_positives"], report["false_negatives"]
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    assert report["precision"] == round(precision, 4)
    assert report["recall"] == round(recall, 4)
    assert report["f1"] == round(f1, 4)
    expected_rules = sum(len(case["expect"]) for case in load_cases())
    assert tp + fn == expected_rules


def test_format_and_percent_sql():
    source = 'def run(cursor, name):\n    cursor.execute("SELECT " + name)\n    cursor.execute("SELECT %s" % name)\n    cursor.execute("SELECT {}".format(name))\n'
    rules = {item.rule_id for item in analyze_ast(source, "q.py")}
    assert rules == {"PP009"}
    assert len(analyze_ast(source, "q.py")) == 3


def test_dedupe_same_rule_line():
    one = make_finding(
        rule_id="PP002",
        path="a.py",
        line=4,
        end_line=4,
        source="x = eval(y)\n",
        evidence="eval",
        severity="high",
        confidence="high",
        origin="confirmed",
    )
    two = one.model_copy(deep=True)
    assert len(dedupe([one, two])) == 1


def test_demo_filters_preexisting_and_safe_fix_clears_them():
    risky = review_diff(demo_diff(), title="demo")
    introduced = {item.rule_id for item in risky.findings}
    prior = {item.rule_id for item in risky.pre_existing}
    assert introduced == {"PP001", "PP003", "PP006"}
    assert "PP002" in prior and "PP005" in prior
    assert "PP002" not in introduced and "PP005" not in introduced
    labels = next(item for item in risky.files if item.path.endswith("labels.py"))
    assert labels.added_lines
    assert not any(item.file.endswith("labels.py") for item in risky.findings)

    fixed = review_diff(safe_fix_diff(), title="fixed")
    assert fixed.findings == []
    assert {item.rule_id for item in fixed.pre_existing} >= {"PP002", "PP005"}


def test_demo_file_matches_generator(tmp_path):
    write_example_files()
    from app.samples import EXAMPLES

    assert (EXAMPLES / "demo_pr.diff").read_text(encoding="utf-8") == demo_diff()
    assert (EXAMPLES / "safe_fix.diff").read_text(encoding="utf-8") == safe_fix_diff()


def test_zip_and_binary_rejected():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as archive:
        archive.writestr("../evil.py", "import os\nos.system(name)\n")
    with pytest.raises(UploadError):
        classify("proj.zip", buf.getvalue())

    good = io.BytesIO()
    with zipfile.ZipFile(good, "w") as archive:
        archive.writestr("pkg/run.py", "import subprocess\nsubprocess.run(f'ls {path}', shell=True)\n")
    kind, files = classify("proj.zip", good.getvalue())
    assert kind == "zip"
    review = review_files(files, title="zip", filename="proj.zip", source="zip")
    assert any(item.rule_id == "PP001" for item in review.findings)

    with pytest.raises(UploadError):
        classify("notes.diff", b"\x00\x01")
    with pytest.raises(UploadError):
        classify("image.png", b"not a diff and not python")


def test_ai_failure_keeps_static_findings(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    def boom(_messages):
        raise TimeoutError("model timeout")

    monkeypatch.setattr("app.ai_layer._complete", boom)
    review = review_diff(demo_diff(), title="ai", enrich=True)
    assert {item.rule_id for item in review.findings} == {"PP001", "PP003", "PP006"}
    assert review.ai_status == "unavailable"
    assert all(item.ai is None for item in review.findings)
    assert "unchanged" in review.ai_message.lower() or "failed" in review.ai_message.lower()


def test_ai_skipped_without_request(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    review = review_diff(demo_diff(), title="plain", enrich=False)
    assert review.ai_status == "off"
    assert review.findings


def test_upload_api(tmp_path, monkeypatch):
    monkeypatch.setenv("PATCHPROOF_DATA", str(tmp_path / "reviews.json"))
    monkeypatch.setenv("PATCHPROOF_NO_SEED", "1")
    from app.main import app

    client = TestClient(app)
    bad = client.post("/api/reviews/text", json={"text": "hello", "title": "bad"})
    assert bad.status_code == 400

    ok = client.post(
        "/api/reviews",
        files={"file": ("demo_pr.diff", demo_diff().encode(), "text/plain")},
        data={"enrich": "false", "title": "uploaded demo"},
    )
    assert ok.status_code == 200
    body = ok.json()
    assert {item["rule_id"] for item in body["findings"]} == {"PP001", "PP003", "PP006"}
    finding_id = body["findings"][0]["id"]
    resolved = client.post(
        f"/api/reviews/{body['id']}/findings/{finding_id}/resolve",
        json={"resolved": True},
    )
    assert resolved.status_code == 200
    assert resolved.json()["summary"]["resolved"] == 1

    stats = client.get("/api/stats")
    assert stats.status_code == 200
    assert stats.json()["reviews"] == 1
    evaluation = client.get("/api/evaluation")
    assert evaluation.json()["sample_count"] == 20
    assert evaluation.json()["f1"] == 1.0
