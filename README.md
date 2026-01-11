# Python Package Verification + Badge Awards

This repo verifies student Python packages and publishes a badge per GitHub repo when checks pass.

## Install

- Python 3.10+ recommended
- Local run: `python -m venv .venv && source .venv/bin/activate && pip install -U pip`

## Usage

1) Add GitHub repo URLs (one per line) to `repos.txt`.
2) Run the verifier:

```bash
python scripts/verify_repos.py --repos repos.txt --badges badges --results results.json
```

Optional report output with badge URLs:

```bash
python scripts/verify_repos.py --repos repos.txt --badges badges --results results.json --report docs/index.html --badge-base-url https://raw.githubusercontent.com/<YOUR_ORG>/<YOUR_REPO>/main/badges
```

3) View the Hall of Fame: https://xiaziyna.github.io/install_award/

## What is checked

- `pyproject.toml` exists
- `README.md` includes the words "install" and "usage"
- `pip install -e .` succeeds in a fresh virtual environment
- `requirements.txt` is installed if present

## GitHub Actions

See `.github/workflows/verify.yml` for the automated workflow that runs the verifier, updates badges, and publishes the Hall of Fame page.
