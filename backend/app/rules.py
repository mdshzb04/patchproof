"""Deterministic Python checks. AST first. Line scan only when the file is partial."""

from __future__ import annotations

import ast
import hashlib
import re
from typing import Iterable

from app.models import EvidenceStep, Finding

SECRET_PREFIXES: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"AKIA[0-9A-Z]{16}"), "AWS access key id pattern"),
    (re.compile(r"sk-(live|proj)-[A-Za-z0-9]{8,}"), "live API key prefix"),
    (re.compile(r"ghp_[A-Za-z0-9]{20,}"), "GitHub personal access token pattern"),
    (re.compile(r"xox[baprs]-[A-Za-z0-9-]{10,}"), "Slack token pattern"),
]
SECRET_NAME = re.compile(
    r"(password|passwd|secret|api_key|apikey|api_token|access_key|private_key|token)",
    re.I,
)
SECRET_DENY = {
    "password",
    "secret",
    "changeme",
    "example",
    "placeholder",
    "xxxxxxxx",
    "testtest",
    "your-api-key",
    "todo",
    "dummy",
    "sample",
    "redacted",
    "none",
    "null",
    "undefined",
    "test",
    "fake",
}

RULES = {
    "PP001": {
        "title": "Shell command with untrusted input",
        "category": "security",
        "impact": "A shell interprets metacharacters. If any part of the command comes from a request, filename, or other caller-controlled value, that caller can run other commands.",
        "recommendation": "Pass the program and arguments as a list. Do not set shell=True.",
        "fix_example": 'subprocess.run(["tar", "czf", "backup.tar.gz", path], check=True)',
    },
    "PP002": {
        "title": "eval or exec on dynamic input",
        "category": "security",
        "impact": "eval and exec run Python from a string. A caller who controls that string can execute arbitrary code in the process.",
        "recommendation": "Parse structured data with json or ast.literal_eval. Keep exec out of request paths.",
        "fix_example": "value = ast.literal_eval(expr)  # only for Python literals",
    },
    "PP003": {
        "title": "Unsafe pickle deserialization",
        "category": "security",
        "impact": "pickle.load reconstructs objects by calling reduce functions stored in the stream. Untrusted pickle bytes can run code during loading.",
        "recommendation": "Accept JSON or another schema-checked format. Reserve pickle for data you signed and stored yourself.",
        "fix_example": "return json.loads(blob)",
    },
    "PP004": {
        "title": "Unsafe YAML load",
        "category": "security",
        "impact": "yaml.load without SafeLoader can construct arbitrary Python objects from the document, including ones that execute code.",
        "recommendation": "Use yaml.safe_load, or pass Loader=yaml.SafeLoader.",
        "fix_example": "return yaml.safe_load(text)",
    },
    "PP005": {
        "title": "Hardcoded credential",
        "category": "security",
        "impact": "A secret in source is copied into git history, logs, and review tools. Anyone with the repo can use it.",
        "recommendation": "Read the secret from the environment or a secret store. Rotate any value that already landed in a diff.",
        "fix_example": 'token = os.environ["BACKUP_TOKEN"]',
    },
    "PP006": {
        "title": "TLS verification disabled",
        "category": "security",
        "impact": "verify=False accepts any certificate. A network attacker can impersonate the remote host.",
        "recommendation": "Leave verification on. Pin a custom CA bundle if the host uses a private certificate.",
        "fix_example": "return requests.get(url, timeout=10)",
    },
    "PP007": {
        "title": "Insecure temporary file",
        "category": "security",
        "impact": "tempfile.mktemp returns a name without creating the file. Another process can create that path first.",
        "recommendation": "Use tempfile.mkstemp or NamedTemporaryFile.",
        "fix_example": "fd, path = tempfile.mkstemp(prefix='job-')",
    },
    "PP008": {
        "title": "Weak cryptographic algorithm",
        "category": "security",
        "impact": "MD5, SHA-1, and ECB mode do not provide the collision or confidentiality properties modern protocols expect.",
        "recommendation": "Use SHA-256 or stronger for integrity, and an authenticated mode such as GCM for encryption. Pass usedforsecurity=False only for a non-security checksum.",
        "fix_example": "return hashlib.sha256(data).hexdigest()",
    },
    "PP009": {
        "title": "SQL built with string interpolation",
        "category": "security",
        "impact": "Values spliced into the SQL string can change the query. Parameter binding keeps them as data.",
        "recommendation": "Pass a constant query and a bound parameter tuple.",
        "fix_example": 'cursor.execute("SELECT id FROM users WHERE name = %s", (name,))',
    },
    "PP010": {
        "title": "Broad exception handler hides the failure",
        "category": "reliability",
        "impact": "except Exception that passes or returns drops timeouts, bugs, and cancelled work. Callers continue as if the step succeeded.",
        "recommendation": "Catch the specific error you can handle, or log it and raise.",
        "fix_example": "except TimeoutError:\n    raise",
    },
}

SHELL_FUNCS = {
    "subprocess.run",
    "subprocess.call",
    "subprocess.Popen",
    "subprocess.check_output",
    "subprocess.check_call",
    "subprocess.getoutput",
    "subprocess.getstatusoutput",
    "os.system",
    "os.popen",
}
ALWAYS_SHELL = {"subprocess.getoutput", "subprocess.getstatusoutput", "os.system", "os.popen"}
PICKLE_FUNCS = {"pickle.load", "pickle.loads", "_pickle.load", "_pickle.loads", "cPickle.load", "cPickle.loads"}
YAML_UNSAFE = {"yaml.load", "yaml.unsafe_load", "yaml.full_load"}


def _snippet(source: str, line: int, radius: int = 1) -> str:
    lines = source.splitlines()
    if line < 1 or line > len(lines):
        return ""
    start = max(1, line - radius)
    end = min(len(lines), line + radius)
    return "\n".join(f"{i}: {lines[i - 1]}" for i in range(start, end + 1))


def _finding_id(rule_id: str, path: str, line: int, evidence: str) -> str:
    digest = hashlib.sha256(f"{rule_id}|{path}|{line}|{evidence}".encode()).hexdigest()[:12]
    return f"F-{digest}"


def _chain(rule_id: str, path: str, line: int, evidence: str, impact: str, recommendation: str, in_diff: bool) -> list[EvidenceStep]:
    where = "Added or modified in this diff" if in_diff else "Present in the file, outside the changed lines"
    meta = RULES[rule_id]
    return [
        EvidenceStep(step="changed_line", label=f"{path}:{line}", detail=where),
        EvidenceStep(step="rule", label=rule_id, detail=meta["title"]),
        EvidenceStep(step="evidence", label="Matched code", detail=evidence),
        EvidenceStep(step="risk", label=meta["category"], detail=impact),
        EvidenceStep(step="fix", label="Suggested fix", detail=recommendation),
    ]


def make_finding(
    *,
    rule_id: str,
    path: str,
    line: int,
    end_line: int,
    source: str,
    evidence: str,
    severity: str,
    confidence: str,
    origin: str,
    bandit_id: str | None = None,
    in_diff: bool = True,
) -> Finding:
    meta = RULES[rule_id]
    return Finding(
        id=_finding_id(rule_id, path, line, evidence),
        rule_id=rule_id,
        title=meta["title"],
        severity=severity,  # type: ignore[arg-type]
        confidence=confidence,  # type: ignore[arg-type]
        category=meta["category"],  # type: ignore[arg-type]
        file=path,
        line=line,
        end_line=end_line,
        snippet=_snippet(source, line),
        evidence=evidence,
        impact=meta["impact"],
        recommendation=meta["recommendation"],
        fix_example=meta["fix_example"],
        origin=origin,  # type: ignore[arg-type]
        in_diff=in_diff,
        bandit_id=bandit_id,
        evidence_chain=_chain(rule_id, path, line, evidence, meta["impact"], meta["recommendation"], in_diff),
    )


def dotted(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = dotted(node.value)
        return f"{base}.{node.attr}" if base else node.attr
    return None


def _const_str(node: ast.AST | None) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _is_dynamic(node: ast.AST | None) -> bool:
    if node is None:
        return True
    if isinstance(node, ast.Constant):
        return False
    if isinstance(node, (ast.List, ast.Tuple)):
        return any(_is_dynamic(elt) for elt in node.elts)
    return True


def _kw_const(node: ast.Call, name: str):
    for kw in node.keywords:
        if kw.arg == name and isinstance(kw.value, ast.Constant):
            return kw.value.value
    return None


def _secret_placeholder(value: str) -> bool:
    lowered = value.strip().lower()
    if len(lowered) < 8:
        return True
    if lowered in SECRET_DENY:
        return True
    if "placeholder" in lowered or "example" in lowered or "changeme" in lowered or "your-" in lowered:
        return True
    if len(set(lowered)) == 1:
        return True
    return False


def _assign_names(target: ast.AST) -> Iterable[str]:
    if isinstance(target, ast.Name):
        yield target.id
    elif isinstance(target, (ast.Tuple, ast.List)):
        for elt in target.elts:
            yield from _assign_names(elt)


def _hides_failure(body: list[ast.stmt]) -> bool:
    if not body:
        return True
    if any(isinstance(stmt, ast.Raise) for stmt in body):
        return False
    return all(isinstance(stmt, (ast.Pass, ast.Continue, ast.Return)) for stmt in body)


def _is_broad(node: ast.AST | None) -> bool:
    if node is None:
        return True
    if isinstance(node, ast.Name) and node.id in {"Exception", "BaseException"}:
        return True
    if isinstance(node, ast.Tuple):
        return any(isinstance(elt, ast.Name) and elt.id in {"Exception", "BaseException"} for elt in node.elts)
    return False


class RuleVisitor(ast.NodeVisitor):
    def __init__(self, source: str, path: str):
        self.source = source
        self.path = path
        self.findings: list[Finding] = []

    def _add(self, rule_id: str, node: ast.AST, evidence: str, severity: str, confidence: str, origin: str) -> None:
        line = getattr(node, "lineno", 1) or 1
        end_line = getattr(node, "end_lineno", line) or line
        self.findings.append(
            make_finding(
                rule_id=rule_id,
                path=self.path,
                line=line,
                end_line=end_line,
                source=self.source,
                evidence=evidence,
                severity=severity,
                confidence=confidence,
                origin=origin,
            )
        )

    def visit_Call(self, node: ast.Call) -> None:
        name = dotted(node.func) or ""
        self._shell(node, name)
        self._eval(node, name)
        self._pickle(node, name)
        self._yaml(node, name)
        self._tls(node, name)
        self._mktemp(node, name)
        self._crypto(node, name)
        self._sql(node, name)
        self._secret_kw(node)
        self.generic_visit(node)

    def visit_Assign(self, node: ast.Assign) -> None:
        if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
            names = [n for t in node.targets for n in _assign_names(t)]
            self._secret_value(node, names, node.value.value)
        self._tls_assign(node)
        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str) and node.target is not None:
            self._secret_value(node, list(_assign_names(node.target)), node.value.value)
        self.generic_visit(node)

    def visit_ExceptHandler(self, node: ast.ExceptHandler) -> None:
        if _is_broad(node.type) and _hides_failure(node.body):
            kind = "bare except" if node.type is None else "except Exception"
            self._add(
                "PP010",
                node,
                f"{kind} swallows the error with pass, continue, or return.",
                "medium",
                "high",
                "confirmed",
            )
        self.generic_visit(node)

    def _shell(self, node: ast.Call, name: str) -> None:
        if name not in SHELL_FUNCS:
            return
        shell_flag = name in ALWAYS_SHELL or _kw_const(node, "shell") is True
        if not shell_flag:
            return
        dynamic = _is_dynamic(node.args[0]) if node.args else True
        if dynamic:
            self._add(
                "PP001",
                node,
                f"{name} uses the shell and the command is not a constant.",
                "critical",
                "high",
                "confirmed",
            )
        else:
            self._add(
                "PP001",
                node,
                f"{name} uses the shell with a constant command. No interpolated input is visible at this call.",
                "medium",
                "medium",
                "needs_investigation",
            )

    def _eval(self, node: ast.Call, name: str) -> None:
        if name not in {"eval", "exec", "builtins.eval", "builtins.exec"}:
            return
        dynamic = _is_dynamic(node.args[0]) if node.args else True
        if dynamic:
            self._add("PP002", node, f"{name}() receives a non-constant argument.", "critical", "high", "confirmed")
        else:
            self._add(
                "PP002",
                node,
                f"{name}() is called with a constant. The call is still dynamic execution.",
                "medium",
                "medium",
                "needs_investigation",
            )

    def _pickle(self, node: ast.Call, name: str) -> None:
        if name in PICKLE_FUNCS:
            self._add("PP003", node, f"{name} deserializes pickle data.", "high", "high", "confirmed")

    def _yaml(self, node: ast.Call, name: str) -> None:
        if name == "yaml.safe_load":
            return
        if name not in YAML_UNSAFE and not name.endswith(".load"):
            return
        if name not in YAML_UNSAFE:
            return
        loader = None
        for kw in node.keywords:
            if kw.arg == "Loader":
                loader = dotted(kw.value) or ""
        if loader and loader.split(".")[-1] in {"SafeLoader", "CSafeLoader"}:
            return
        self._add(
            "PP004",
            node,
            f"{name} is used without SafeLoader.",
            "high",
            "high",
            "confirmed",
        )

    def _tls(self, node: ast.Call, name: str) -> None:
        if _kw_const(node, "verify") is False:
            self._add("PP006", node, f"{name or 'call'} passes verify=False.", "high", "high", "confirmed")
        if name == "ssl._create_unverified_context":
            self._add("PP006", node, "ssl._create_unverified_context disables certificate checks.", "high", "high", "confirmed")

    def _tls_assign(self, node: ast.Assign) -> None:
        value = dotted(node.value) if not isinstance(node.value, ast.Constant) else ""
        if value and value.endswith("CERT_NONE"):
            self._add("PP006", node, "Certificate verification mode is set to CERT_NONE.", "high", "high", "confirmed")

    def _mktemp(self, node: ast.Call, name: str) -> None:
        if name == "tempfile.mktemp":
            self._add("PP007", node, "tempfile.mktemp allocates a name before the file exists.", "medium", "high", "confirmed")

    def _crypto(self, node: ast.Call, name: str) -> None:
        if _kw_const(node, "usedforsecurity") is False:
            return
        weak = name in {"hashlib.md5", "hashlib.sha1", "hashlib.md4"}
        if name == "hashlib.new" and node.args:
            algo = _const_str(node.args[0])
            weak = algo in {"md5", "sha1", "md4"}
        if weak:
            self._add("PP008", node, f"{name} is a weak hash for security use.", "medium", "medium", "confirmed")
        func = dotted(node.func) or ""
        if func.endswith(".new"):
            for arg in list(node.args) + [kw.value for kw in node.keywords]:
                label = dotted(arg) or ""
                if label.endswith("MODE_ECB"):
                    self._add("PP008", node, "Cipher is constructed with MODE_ECB.", "medium", "medium", "confirmed")
                    break

    def _sql(self, node: ast.Call, name: str) -> None:
        leaf = name.split(".")[-1]
        if leaf not in {"execute", "executemany", "executescript"} or not node.args:
            return
        arg = node.args[0]
        if isinstance(arg, ast.JoinedStr):
            how = "an f-string"
        elif isinstance(arg, ast.BinOp) and isinstance(arg.op, (ast.Mod, ast.Add)):
            how = "string concatenation or percent formatting"
        elif isinstance(arg, ast.Call) and isinstance(arg.func, ast.Attribute) and arg.func.attr == "format":
            how = "str.format"
        else:
            return
        self._add("PP009", node, f"{name} builds SQL with {how}.", "high", "high", "confirmed")

    def _secret_kw(self, node: ast.Call) -> None:
        for kw in node.keywords:
            if not kw.arg or not SECRET_NAME.search(kw.arg):
                continue
            value = _const_str(kw.value)
            if value and not _secret_placeholder(value):
                self._add(
                    "PP005",
                    node,
                    f"Keyword {kw.arg} is a string literal.",
                    "high",
                    "medium",
                    "confirmed",
                )

    def _secret_value(self, node: ast.AST, names: list[str], value: str) -> None:
        if _secret_placeholder(value):
            return
        prefix_hit = next((label for pattern, label in SECRET_PREFIXES if pattern.search(value)), None)
        name_hit = next((n for n in names if SECRET_NAME.search(n)), None)
        if prefix_hit:
            self._add("PP005", node, f"String matches a {prefix_hit}.", "high", "high", "confirmed")
        elif name_hit:
            self._add(
                "PP005",
                node,
                f"{name_hit} is assigned a string literal.",
                "high",
                "medium",
                "confirmed",
            )


def analyze_ast(source: str, path: str) -> list[Finding]:
    tree = ast.parse(source)
    visitor = RuleVisitor(source, path)
    visitor.visit(tree)
    return visitor.findings


_LINE_RULES: list[tuple[str, re.Pattern[str], str, str, str, str]] = [
    ("PP001", re.compile(r"shell\s*=\s*True"), "Added line sets shell=True.", "high", "medium", "confirmed"),
    ("PP001", re.compile(r"\bos\.system\s*\("), "Added line calls os.system.", "high", "medium", "confirmed"),
    ("PP002", re.compile(r"(?<![\w.])(eval|exec)\s*\("), "Added line calls eval or exec.", "high", "medium", "confirmed"),
    ("PP003", re.compile(r"\bpickle\.(loads|load)\s*\("), "Added line calls pickle load.", "high", "medium", "confirmed"),
    ("PP004", re.compile(r"\byaml\.(load|unsafe_load|full_load)\s*\("), "Added line calls unsafe YAML load.", "high", "medium", "confirmed"),
    ("PP006", re.compile(r"verify\s*=\s*False"), "Added line sets verify=False.", "high", "medium", "confirmed"),
    ("PP007", re.compile(r"\btempfile\.mktemp\s*\("), "Added line calls tempfile.mktemp.", "medium", "medium", "confirmed"),
    ("PP008", re.compile(r"\bhashlib\.(md5|sha1|md4)\s*\("), "Added line uses a weak hash.", "medium", "low", "needs_investigation"),
    ("PP009", re.compile(r"\.(execute|executemany|executescript)\s*\(\s*f['\"]"), "Added line executes an f-string SQL query.", "high", "medium", "confirmed"),
    ("PP010", re.compile(r"except\s+(Exception|BaseException)\s*:"), "Added line uses a broad except.", "low", "low", "needs_investigation"),
]


def scan_added_lines(path: str, line_text: dict[int, str], added_lines: set[int]) -> list[Finding]:
    """Fallback for partial diffs. Matches only lines the patch added."""
    findings: list[Finding] = []
    if not line_text:
        return findings
    last = max(line_text)
    source = "\n".join(line_text.get(i, "") for i in range(1, last + 1))
    for number in sorted(added_lines):
        if number not in line_text:
            continue
        text = line_text[number]
        stripped = text.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if "literal_eval" in text or "safe_load" in text or "SafeLoader" in text:
            continue
        if "usedforsecurity=False" in text.replace(" ", ""):
            continue
        for rule_id, pattern, evidence, severity, confidence, origin in _LINE_RULES:
            if pattern.search(text):
                findings.append(
                    make_finding(
                        rule_id=rule_id,
                        path=path,
                        line=number,
                        end_line=number,
                        source=source,
                        evidence=evidence + " File was not reconstructed as a complete module, so this is line evidence.",
                        severity=severity,
                        confidence=confidence,
                        origin=origin,
                    )
                )
                break
        else:
            for pattern, label in SECRET_PREFIXES:
                if pattern.search(text):
                    findings.append(
                        make_finding(
                            rule_id="PP005",
                            path=path,
                            line=number,
                            end_line=number,
                            source=source,
                            evidence=f"Added line matches a {label}.",
                            severity="high",
                            confidence="medium",
                            origin="confirmed",
                        )
                    )
                    break
    return findings


def dedupe(findings: list[Finding]) -> list[Finding]:
    seen: set[tuple[str, str, int]] = set()
    kept: list[Finding] = []
    for finding in findings:
        key = (finding.rule_id, finding.file, finding.line)
        if key in seen:
            continue
        seen.add(key)
        kept.append(finding)
    return kept
