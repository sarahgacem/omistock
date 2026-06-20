# Recreating the virtualenv

The local `.venv/` (≈156 MB) was removed to shrink the workspace for download.
It is fully reproducible from the pinned requirements:

```bash
cd omistock
python3 -m venv .venv
./.venv/bin/pip install --upgrade pip
./.venv/bin/pip install -r backend/requirements.txt
./.venv/bin/pip install -r backend/requirements-test.txt   # for the test suite
```

Then run the tests (28 should pass) and boot check as documented in the review report:

```bash
./.venv/bin/python -m pytest
```
