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
        "label": "python package",
        "message": status_message,
        "color": "brightgreen" if ok else "red",
        "labelColor": "2b3a42",
        "logo": "python",
        "logoColor": "white",
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

    ok, reason = ensure_readme(repo_dir)
    if not ok:
        return RepoResult(repo_url, False, reason)

    venv_dir = work_dir / "venv"
    ok, reason = create_venv(venv_dir)
    if not ok:
        return RepoResult(repo_url, False, reason)

    ok, reason = install_editable(venv_dir, repo_dir)
    if not ok:
        return RepoResult(repo_url, False, reason)

    badge_path = write_badge(badges_dir, repo_url, True)
    return RepoResult(repo_url, True, "ok", badge_path)


def write_report(
    report_path: Path,
    results: List[RepoResult],
    badge_base_url: str,
) -> None:
    lines = [
        "# Badge Report",
        "",
        "| Repo | Status | Badge |",
        "| --- | --- | --- |",
    ]
    for result in results:
        badge_url = shields_badge_url(badge_base_url, result.url)
        status = "PASS" if result.ok else "FAIL"
        badge_md = f"![badge]({badge_url})"
        lines.append(f"| {result.url} | {status} | {badge_md} |")
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


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
