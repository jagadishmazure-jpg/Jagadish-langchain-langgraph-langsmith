"""10 Retrieval Building Blocks: load, split, embed, search, and make retrieval agentic.

Client: Quillmere Home Loans' underwriting assistant. Loan officers ask policy questions ("can a gift
cover the whole down payment on a second home?") and need an answer grounded in the current
underwriting guidelines with the source named. The scenario measures retrieval quality on a labelled
question set before any model sees the chunks.
"""

from __future__ import annotations

import re
from pathlib import Path

from langchain.agents import create_agent
from langchain.tools import tool
from langchain_core.documents import Document
from langchain_core.vectorstores import InMemoryVectorStore
from langchain_text_splitters import RecursiveCharacterTextSplitter

from lcstack.core.companies import MORTGAGE
from lcstack.core.embeddings import stems
from lcstack.core.models import embeddings
from lcstack.core.scripted import Intent, Playbook, Turn, scripted
from lcstack.scenarios import Meta

META = Meta(10, "Retrieval Building Blocks", "Loader, RecursiveCharacterTextSplitter, embeddings, InMemoryVectorStore, retriever, retriever as a @tool, recall@k and MRR",
            f"{MORTGAGE}: underwriting-guideline assistant", "mortgage", "retrieval")  # fmt: skip

CORPUS = Path(__file__).resolve().parents[1] / "data" / "quillmere_guidelines"

# question -> the guideline file that answers it (labelled by hand)
QUESTIONS = [
    ("How many pay stubs does a salaried borrower need?", "income-verification.md"),
    ("How is self-employed income averaged?", "income-verification.md"),
    ("What is the maximum debt-to-income ratio?", "debt-to-income.md"),
    ("How are deferred student loans counted in DTI?", "debt-to-income.md"),
    ("How much does a rate lock extension cost?", "rate-locks.md"),
    ("Can the borrower float down if rates fall?", "rate-locks.md"),
    ("What happens when the appraisal comes in below the contract price?", "appraisal.md"),
    ("Can a gift cover the down payment on a second home?", "gift-funds.md"),
    ("How long after a bankruptcy can someone apply?", "credit-history.md"),
    ("How many months of reserves does an investment property need?", "reserves.md"),
    ("Are condominiums eligible?", "property-types.md"),
    # paraphrases with little word overlap: a lexical embedding should struggle here
    ("Can my parents help me pay for the house?", "gift-funds.md"),
    ("How much cash must be left in the bank after we buy?", "reserves.md"),
    ("Is a farm okay to finance?", "property-types.md"),
]


def load() -> list[Document]:
    return [Document(page_content=p.read_text(), metadata={"source": p.name}) for p in sorted(CORPUS.glob("*.md"))]


def build_store(chunk_size: int = 800, chunk_overlap: int = 100) -> tuple[InMemoryVectorStore, int]:
    splitter = RecursiveCharacterTextSplitter(chunk_size=chunk_size, chunk_overlap=chunk_overlap)
    chunks = splitter.split_documents(load())
    store = InMemoryVectorStore(embeddings())
    store.add_documents(chunks)
    return store, len(chunks)


def evaluate(store: InMemoryVectorStore, k: int = 5) -> dict:
    retriever = store.as_retriever(search_kwargs={"k": k})
    ranks = []
    for q, gold in QUESTIONS:
        sources = [d.metadata["source"] for d in retriever.invoke(q)]
        ranks.append(sources.index(gold) + 1 if gold in sources else None)
    n = len(ranks)
    return {
        "hit@1": sum(1 for r in ranks if r == 1) / n,
        "hit@3": sum(1 for r in ranks if r and r <= 3) / n,
        f"hit@{k}": sum(1 for r in ranks if r) / n,
        "mrr": sum(1 / r for r in ranks if r) / n,
        "misses": [q for (q, _), r in zip(QUESTIONS, ranks, strict=True) if not r],
        "ranks": ranks,
    }


def retriever_tool(store: InMemoryVectorStore):
    @tool
    def search_guidelines(query: str) -> str:
        """Search Quillmere's underwriting guidelines. Returns passages with their source file."""
        docs = store.as_retriever(search_kwargs={"k": 2}).invoke(query)
        return "\n\n".join(f"[{d.metadata['source']}] {d.page_content}" for d in docs)

    return search_guidelines


def best_sentences(question: str, passages: str, n: int = 2) -> tuple[str, str] | None:
    """Extractive answer: the ``n`` sentences of the top passage sharing the most word stems with the question."""
    q = set(stems(question))
    m = re.match(r"\[(.+?)\] (.*?)(?:\n\n\[|$)", passages, re.S)
    if not m:
        return None
    sents = [x.strip() for x in re.split(r"(?<=[.])\s+", re.sub(r"# .+?\n", "", m.group(2))) if x.strip()]
    scored = sorted(range(len(sents)), key=lambda i: -len(q & set(stems(sents[i]))))[:n]
    keep = [sents[i] for i in sorted(scored) if q & set(stems(sents[i]))]
    return (" ".join(keep), m.group(1)) if keep else None


def _grounded_answer(t: Turn) -> str:
    hit = best_sentences(t.last_human, t.results.get("search_guidelines", ""))
    return f"{hit[0]} (source: {hit[1]})" if hit else "I could not find that in the guidelines."


PLAYBOOK = Playbook(intents=[Intent("ask", r".", steps=[lambda t: ("search_guidelines", {"query": t.last_human})], answer=_grounded_answer)])


def run() -> list[str]:
    docs = load()
    out = [f"{MORTGAGE} - underwriting-guideline retrieval", "", f"loaded {len(docs)} guideline files from {CORPUS.name}/"]
    out.append(f"{'chunking':<16} {'chunks':>6} {'hit@1':>6} {'hit@3':>6} {'hit@5':>6} {'MRR':>6}")
    best = None
    for size, overlap in [(800, 100), (300, 50), (150, 30)]:
        store, n = build_store(size, overlap)
        m = evaluate(store)
        best = best or (store, m)
        out.append(f"{f'{size}/{overlap}':<16} {n:>6} {m['hit@1']:>6.2f} {m['hit@3']:>6.2f} {m['hit@5']:>6.2f} {m['mrr']:>6.2f}")
    store, m = best
    out.append(f"embedding: {type(store.embedding).__name__} (lexical, offline); questions: {len(QUESTIONS)}")
    out.append(f"misses at k=5 with 800/100: {m['misses'] or 'none'}")
    out.append(f"ranks per question (None = not in top 5): {m['ranks']}")
    agent = create_agent(scripted(PLAYBOOK, name="underwriting-assistant"), [retriever_tool(store)])
    q = "Can a gift cover the down payment on a second home?"
    out += [
        "",
        f"agentic retrieval (retriever wrapped in @tool) - {q}",
        f"  {agent.invoke({'messages': [{'role': 'user', 'content': q}]})['messages'][-1].content}",
    ]
    return out
