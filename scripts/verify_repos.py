#!/usr/bin/env python3
import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Tuple
from urllib.parse import quote


@dataclass
class RepoResult:
    url: str
    ok: bool
    reason: str
    badge_path: Path | None = None


def run(cmd: List[str], cwd: Path | None = None) -> Tuple[int, str, str]:
    proc = subprocess.run(
        cmd,
        cwd=str(cwd) if cwd else None,
        text=True,
        capture_output=True,
    )
    return proc.returncode, proc.stdout, proc.stderr


def read_repo_list(path: Path) -> List[str]:
    repos: List[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        repos.append(line)
    return repos


def normalize_repo_slug(url: str) -> str:
    match = re.search(r"github\.com/([^/]+)/([^/]+?)(?:\.git)?$", url)
    if not match:
        return re.sub(r"[^A-Za-z0-9._-]+", "_", url)
    owner, repo = match.group(1), match.group(2)
    return f"{owner}__{repo}"


def ensure_readme(repo_dir: Path) -> Tuple[bool, str]:
    readme = repo_dir / "README.md"
    if not readme.exists():
        return False, "missing README.md"
    text = readme.read_text(encoding="utf-8", errors="ignore").lower()
    if "install" not in text or "usage" not in text:
        return False, "README.md must include install and usage"
    return True, ""


def ensure_pyproject(repo_dir: Path) -> Tuple[bool, str]:
    if not (repo_dir / "pyproject.toml").exists():
        return False, "missing pyproject.toml"
    return True, ""


def create_venv(venv_dir: Path) -> Tuple[bool, str]:
    code, out, err = run([sys.executable, "-m", "venv", str(venv_dir)])
    if code != 0:
        return False, f"venv creation failed: {err.strip() or out.strip()}"
    return True, ""


def venv_python(venv_dir: Path) -> Path:
    if os.name == "nt":
        return venv_dir / "Scripts" / "python"
    return venv_dir / "bin" / "python"


def install_editable(venv_dir: Path, repo_dir: Path) -> Tuple[bool, str]:
    py = venv_python(venv_dir)
    code, out, err = run([str(py), "-m", "pip", "install", "-U", "pip"])
    if code != 0:
        return False, f"pip upgrade failed: {err.strip() or out.strip()}"

    requirements = repo_dir / "requirements.txt"
    if requirements.exists():
        code, out, err = run([str(py), "-m", "pip", "install", "-r", str(requirements)])
        if code != 0:
            return False, f"requirements install failed: {err.strip() or out.strip()}"

    code, out, err = run([str(py), "-m", "pip", "install", "-e", "."], cwd=repo_dir)
    if code != 0:
        return False, f"pip install -e . failed: {err.strip() or out.strip()}"

    return True, ""


def write_badge(badges_dir: Path, repo_url: str, ok: bool) -> Path:
    slug = normalize_repo_slug(repo_url)
    badge_path = badges_dir / f"{slug}.json"
    status_message = "verified" if ok else "failed"
    payload = {
        "schemaVersion": 1,
        "label": "package",
        "message": status_message,
        "color": "brightgreen" if ok else "red",
    }
    badge_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return badge_path


def shields_badge_url(badge_base_url: str, repo_url: str) -> str:
    slug = normalize_repo_slug(repo_url)
    raw_url = f"{badge_base_url.rstrip('/')}/{slug}.json"
    return (
        "https://img.shields.io/endpoint"
        f"?url={quote(raw_url, safe='')}&style=flat-square"
    )


def verify_repo(repo_url: str, work_dir: Path, badges_dir: Path) -> RepoResult:
    repo_dir = work_dir / "repo"
    code, out, err = run(["git", "clone", "--depth", "1", repo_url, str(repo_dir)])
    if code != 0:
        return RepoResult(repo_url, False, f"git clone failed: {err.strip() or out.strip()}")

    ok, reason = ensure_pyproject(repo_dir)
    if not ok:
        return RepoResult(repo_url, False, reason)

    try:
        ok, reason = ensure_readme(repo_dir)
    except Exception as exc:  # defensive: avoid crashing on unexpected README issues
        return RepoResult(repo_url, False, f"README check error: {exc}")
    if not ok:
        return RepoResult(repo_url, False, reason)

    venv_dir = work_dir / "venv"
    ok, reason = create_venv(venv_dir)
    if not ok:
        return RepoResult(repo_url, False, reason)

    try:
        ok, reason = install_editable(venv_dir, repo_dir)
    except Exception as exc:  # catch unexpected installer crashes
        return RepoResult(repo_url, False, f"pip install error: {exc}")
    if not ok:
        return RepoResult(repo_url, False, reason)

    badge_path = write_badge(badges_dir, repo_url, True)
    return RepoResult(repo_url, True, "ok", badge_path)


def write_report(
    report_path: Path,
    results: List[RepoResult],
    badge_base_url: str,
) -> None:
    cards = []
    for result in results:
        badge_url = shields_badge_url(badge_base_url, result.url)
        status = "PASS" if result.ok else "FAIL"
        icon = "&#10003;"  # checkmark
        cards.append(
            "\n".join(
                [
                    "<article class=\"card\">",
                    f"  <a class=\"repo\" href=\"{result.url}\">{result.url}</a>",
                    f"  <div class=\"status {status.lower()}\"><span class=\"icon\">{icon}</span>{status}</div>",
                    f"  <img class=\"badge\" src=\"{badge_url}\" alt=\"badge\" />",
                    "</article>",
                ]
            )
        )

    html = "\n".join(
        [
            "<!doctype html>",
            "<html lang=\"en\">",
            "<head>",
            "  <meta charset=\"utf-8\" />",
            "  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />",
            "  <title>Hall of Fame</title>",
            "  <style>",
            "    :root {",
            "      --bg-1: #ffe8d6;",
            "      --bg-2: #cce3de;",
            "      --ink: #1f2933;",
            "      --accent: #ff6b6b;",
            "      --accent-2: #3d5a80;",
            "      --card: #ffffff;",
            "      --shadow: rgba(31, 41, 51, 0.12);",
            "    }",
            "    * { box-sizing: border-box; }",
            "    body {",
            "      margin: 0;",
            "      font-family: \"Trebuchet MS\", \"Gill Sans\", \"DejaVu Sans\", sans-serif;",
            "      color: var(--ink);",
            "      background: radial-gradient(circle at top left, var(--bg-1), transparent 60%),",
            "                  radial-gradient(circle at bottom right, var(--bg-2), transparent 55%),",
            "                  linear-gradient(135deg, #fef9ef, #f4f1de);",
            "      min-height: 100vh;",
            "    }",
            "    header {",
            "      padding: 48px 24px 24px;",
            "      text-align: center;",
            "    }",
            "    h1 {",
            "      margin: 0 0 8px;",
            "      font-size: clamp(2rem, 4vw, 3.2rem);",
            "      letter-spacing: 0.02em;",
            "    }",
            "    p.subtitle {",
            "      margin: 0;",
            "      font-size: 1.05rem;",
            "      color: var(--accent-2);",
            "    }",
            "    .grid {",
            "      display: grid;",
            "      gap: 16px;",
            "      padding: 16px 24px 64px;",
            "      grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));",
            "    }",
            "    .card {",
            "      background: var(--card);",
            "      padding: 16px;",
            "      border-radius: 16px;",
            "      box-shadow: 0 10px 25px var(--shadow);",
            "      display: grid;",
            "      gap: 10px;",
            "      align-content: start;",
            "      position: relative;",
            "      overflow: hidden;",
            "      animation: floatIn 400ms ease-out both;",
            "    }",
            "    .card::after {",
            "      content: \"\";",
            "      position: absolute;",
            "      inset: auto -20% 0;",
            "      height: 6px;",
            "      background: linear-gradient(90deg, var(--accent), var(--accent-2));",
            "    }",
            "    .repo {",
            "      text-decoration: none;",
            "      color: var(--ink);",
            "      font-weight: 700;",
            "      word-break: break-word;",
            "    }",
            "    .status {",
            "      font-size: 0.9rem;",
            "      font-weight: 700;",
            "      text-transform: uppercase;",
            "      letter-spacing: 0.08em;",
            "      display: inline-flex;",
            "      align-items: center;",
            "      gap: 6px;",
            "    }",
            "    .status .icon { font-size: 1.1rem; }",
            "    .status.pass { color: #2a9d8f; }",
            "    .status.pass .icon { color: #2a9d8f; }",
            "    .status.fail { color: #e63946; }",
            "    .status.fail .icon { color: #e63946; }",
            "    .badge {",
            "      width: fit-content;",
            "      max-width: 100%;",
            "      height: auto;",
            "    }",
            "    @keyframes floatIn {",
            "      from { transform: translateY(12px); opacity: 0; }",
            "      to { transform: translateY(0); opacity: 1; }",
            "    }",
            "  </style>",
            "</head>",
            "<body>",
            "  <header>",
            "    <h1>Hall of Fame</h1>",
            "    <p class=\"subtitle\">Verified Python packages and their badges.</p>",
            "  </header>",
            "  <main class=\"grid\">",
            "\n".join(cards) if cards else "    <p>No repos verified yet.</p>",
            "  </main>",
            "</body>",
            "</html>",
        ]
    )
    report_path.write_text(html + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repos", required=True, type=Path)
    parser.add_argument("--badges", required=True, type=Path)
    parser.add_argument("--results", required=True, type=Path)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--badge-base-url", type=str)
    args = parser.parse_args()

    repos = read_repo_list(args.repos)
    args.badges.mkdir(parents=True, exist_ok=True)

    results: List[RepoResult] = []
    for repo_url in repos:
        with tempfile.TemporaryDirectory(prefix="verify-") as tmp:
            work_dir = Path(tmp)
            result = verify_repo(repo_url, work_dir, args.badges)
            if not result.ok:
                write_badge(args.badges, repo_url, False)
            results.append(result)

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total": len(results),
        "passed": sum(1 for r in results if r.ok),
        "failed": [
            {"url": r.url, "reason": r.reason}
            for r in results
            if not r.ok
        ],
    }
    args.results.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    if args.report and args.badge_base_url:
        write_report(args.report, results, args.badge_base_url.rstrip("/"))

    for r in results:
        status = "PASS" if r.ok else "FAIL"
        print(f"{status} {r.url} {r.reason}")

    return 0 if all(r.ok for r in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
