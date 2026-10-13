# datasets

| File | What it is |
|---|---|
| `support_desk.jsonl` | 35 labelled capstone cases: `inputs` (question, customer_id) and reference `outputs` (route, tools, must_include, source, hitl, reviewer decision, attack type) |

Loaded by `lcstack.capstone.evals.load_examples()` as `langsmith.schemas.Example` objects with stable ids.
With a LangSmith account they can be uploaded with `Client.create_examples`.
