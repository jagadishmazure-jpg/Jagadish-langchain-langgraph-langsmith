# scripts

| File | What it does |
|---|---|
| `render_docs.py` | writes the scenario READMEs and the generated blocks in docs from real runs; `--check` is the CI doc-drift check |
| `scenario_notes.py` | hand-written notes per scenario used by the renderer |
| `agent_server_smoke.py` | starts `langgraph dev` on localhost and drives both graphs through the SDK (CI) |
| `overlap_check.py` | originality check: 8-word overlaps between repo text and local reference files that are never committed |
