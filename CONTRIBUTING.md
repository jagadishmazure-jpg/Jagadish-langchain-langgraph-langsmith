# Contributing

```bash
uv venv -p 3.13 && source .venv/bin/activate
uv pip sync requirements.lock && uv pip install --no-deps -e .
ruff check . && ruff format --check .
pytest -q
lcstack gate
python scripts/render_docs.py --check
```

- Keep everything offline: no test may need a key or the network (the test suite blocks sockets).
- Scenario READMEs are generated: edit the module docstring or `scripts/scenario_notes.py`, then run
  `python scripts/render_docs.py`.
- Do not tune the dataset to the results. If a change moves a metric, explain it in the PR; raising
  `evals/baseline.json` is a reviewed change.
- Companies are fictional. Do not add real customer data, real identifiers or copied reference text;
  `scripts/overlap_check.py` checks originality against local reference files that are never committed.
- After changing dependencies: `uv pip compile pyproject.toml --extra dev --extra azure -p 3.13 -o requirements.lock`.
