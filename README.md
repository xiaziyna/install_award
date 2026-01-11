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
python scripts/verify_repos.py --repos repos.txt --badges badges --results results.json --report badge-report.md --badge-base-url https://raw.githubusercontent.com/<YOUR_ORG>/<YOUR_REPO>/main/badges
```

3) Each repo gets a badge JSON in `badges/`. Use shields.io to render it:

```
https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/<YOUR_ORG>/<YOUR_REPO>/main/badges/<owner>__<repo>.json
```

## What is checked

- `pyproject.toml` exists
- `README.md` includes the words "install" and "usage"
- `pip install -e .` succeeds in a fresh virtual environment
- `requirements.txt` is installed if present

## GitHub Actions

See `.github/workflows/verify.yml` for the automated workflow that runs the verifier and commits badge JSON files back to this repo.

The workflow also writes `badge-report.md` with clickable badge previews.
