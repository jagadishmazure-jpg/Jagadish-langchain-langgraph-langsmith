"""20 Functional API: durable workflows written as plain Python with @entrypoint and @task.

Client: Quillmere Home Loans' nightly rate-lock digest. For every lock expiring within 10 days the job
fetches the loan from the pipeline system (slow), drafts an extension recommendation, then pauses for a
secondary-marketing manager to approve the batch. When the job resumes the next morning, the fetches
already done are not repeated, because finished tasks are checkpointed.
"""

from __future__ import annotations

import time

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.func import entrypoint, task
from langgraph.types import Command, interrupt

from lcstack.core.companies import MORTGAGE
from lcstack.scenarios import Meta

META = Meta(20, "Functional API", "@entrypoint with a checkpointer, @task futures in parallel, interrupt inside a workflow, tasks not re-run on resume, entrypoint.final",
            f"{MORTGAGE}: nightly rate-lock extension digest", "mortgage", "functional-api")  # fmt: skip

LOCKS = {"QH-4471": (9, 12), "QH-4502": (3, 15), "QH-4519": (6, 8), "QH-4533": (1, 19)}  # (lock days left, closing in days)
FETCHES: list[str] = []


@task
def fetch_loan(loan_id: str) -> dict:
    FETCHES.append(loan_id)
    time.sleep(0.05)  # stands in for a slow pipeline-system call; tasks run concurrently
    days_left, closing_in = LOCKS[loan_id]
    return {"loan_id": loan_id, "days_left": days_left, "closing_in": closing_in}


@task
def recommend(loan: dict) -> str:
    gap = loan["closing_in"] - loan["days_left"]
    return f"{loan['loan_id']}: extend {7 if gap <= 7 else 14} days (lock ends in {loan['days_left']}, closing in {loan['closing_in']})"


@entrypoint(checkpointer=InMemorySaver())
def nightly_digest(loan_ids: list[str], *, previous: int | None = None) -> entrypoint.final[dict, int]:
    loans = [f.result() for f in [fetch_loan(i) for i in loan_ids]]  # futures: fetched in parallel
    recs = [f.result() for f in [recommend(loan) for loan in loans]]
    decision = interrupt({"approve_extensions": recs, "approved_last_run": previous})
    approved = recs if decision == "approve all" else [r for r in recs if r.split(":")[0] in decision]
    # return value to the caller vs. value saved for the next run on this thread
    return entrypoint.final(value={"approved": approved, "held": len(recs) - len(approved)}, save=len(approved))


def run() -> list[str]:
    FETCHES.clear()
    cfg = {"configurable": {"thread_id": "digest-night-1"}}
    out = [f"{MORTGAGE} - nightly rate-lock digest (Functional API)", ""]
    paused = nightly_digest.invoke(list(LOCKS), cfg)
    recs = paused["__interrupt__"][0].value["approve_extensions"] if isinstance(paused, dict) else []
    out.append(f"night run: fetched {len(FETCHES)} loans, then paused for approval of {len(recs)} recommendations:")
    out += [f"  {r}" for r in recs]
    before = len(FETCHES)
    result = nightly_digest.invoke(Command(resume=["QH-4502", "QH-4533"]), cfg)
    out.append(f"morning resume (approve two): {result}")
    out.append(f"loan fetches during the resume: {len(FETCHES) - before} (finished tasks were read from the checkpoint)")
    night2 = nightly_digest.invoke(["QH-4471"], cfg)
    out.append(
        f"next night, same thread: the workflow receives previous={night2['__interrupt__'][0].value['approved_last_run']} (the save= value, not the return value)"
    )
    return out
