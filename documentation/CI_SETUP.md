# CI/CD Setup

This project uses **GitHub Actions** for continuous integration. The workflow automatically runs tests, linting, and builds on every push and pull request.

## What Runs On Each Commit

### 1. **Test Suite** (Multi-platform)
- Runs on **Ubuntu** and **Windows** (Python 3.11 & 3.12)
- Executes: `pytest tests/ --tb=short -q --cov=src`
- Uploads coverage to Codecov (main branch only)
- **Fails if**: Any test fails or coverage drops significantly

### 2. **Regression Checks** (Ubuntu)
- Runs: `python tools/run_regression.py`
- Validates architecture and expected behavior
- **Fails if**: Any regression detected

### 3. **Linting** (Embedded in test step)
- Uses **Ruff** for fast Python linting
- Checks for: syntax errors, undefined names, unused imports, whitespace
- Configuration: `pyproject.toml` (`[tool.ruff]` section)
- **Ignores**: Long lines (E501), some style rules

### 4. **Build** (Windows only, runs after tests pass)
- Runs: `python build.py --no-backup`
- Uses **PyInstaller** to create the `.exe`
- Uploads artifact to GitHub (retained 30 days)
- Verifies `.exe` was created and shows file size

## Local Testing Before Push

Run these locally to catch issues early:

```bash
# Run all tests
pytest tests/ --tb=short -q

# Run linting
ruff check src/ tests/

# Run regression checks
python tools/run_regression.py
```

Or run everything at once:
```bash
pytest tests/ && python tools/run_regression.py && ruff check src/ tests/
```

## Configuration Files

### `.github/workflows/ci.yml`
Main workflow file. Defines all jobs and steps.

**Key settings:**
- **Triggers**: Push to `main` + all PRs
- **Python versions**: 3.11, 3.12
- **OS matrix**: Ubuntu, Windows

### `pyproject.toml`
Python project metadata and tool configurations.

**Sections:**
- `[project]` — package info, dependencies
- `[tool.ruff]` — linting rules
- `[tool.pytest.ini_options]` — test discovery
- `[tool.coverage]` — code coverage settings

## Viewing Results

### GitHub Actions Tab
1. Go to your repository on GitHub
2. Click **Actions** tab
3. Select a workflow run to see detailed logs
4. Each job (test, regression, build) can be expanded
5. Artifacts (`.exe`) can be downloaded from the run summary

### Pull Request Checks
- Checks appear at the bottom of PR with ✓ (pass) or ✗ (fail)
- Click "Details" to see logs for a specific check
- PR cannot merge if any check fails

## Troubleshooting

### "Tests failed locally but pass in CI"
- **Cause**: Python version or dependency difference
- **Fix**: 
  - `pip install --upgrade -r requirements.txt`
  - Run `pytest tests/` locally with fresh environment
  - Check Python version: `python --version`

### "Linting passes locally but fails in CI"
- **Cause**: Different Ruff version
- **Fix**: `pip install --upgrade ruff`

### "Build fails in CI but works locally"
- **Cause**: Missing dependencies or PyInstaller version difference
- **Fix**:
  - Check `build.py` logs in GitHub Actions
  - Ensure `requirements.txt` includes all runtime deps
  - Try local build: `python build.py --no-backup`

### Disable a check temporarily
Edit `.github/workflows/ci.yml` and comment out the step. **Commit the change** — this is tracked in git.

## Adding New Tests

1. Create `tests/test_name.py`
2. Add test functions: `def test_something():`
3. Push to a branch
4. CI runs automatically
5. Fix any failures before merging

## Customization

### Change Python versions
Edit `.github/workflows/ci.yml`, line 11:
```yaml
python-version: ['3.11', '3.12']  # Add/remove as needed
```

### Add linting rules
Edit `pyproject.toml`, `[tool.ruff.lint]` section:
```toml
select = ["E", "F", "W", "I"]  # Add "I" for import sorting
```

### Adjust coverage threshold
Edit `.github/workflows/ci.yml` or `pyproject.toml`.

### Include build on main branch only
Edit `.github/workflows/ci.yml`, add to `build` job:
```yaml
if: github.ref == 'refs/heads/main'
```

## Skipping CI (Not Recommended)

Add `[skip ci]` to commit message to skip workflows:
```bash
git commit -m "Minor doc fix [skip ci]"
```

**Use sparingly** — CI catches real bugs.
