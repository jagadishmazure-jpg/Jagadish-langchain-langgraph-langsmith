import re
import subprocess
from pathlib import Path

import pytest

FILES = subprocess.run(["git", "ls-files", "--cached", "--others", "--exclude-standard"], capture_output=True, text=True, check=True).stdout.split()
MD = [Path(f) for f in FILES if f.endswith(".md") and Path(f).exists()]
TEXT = [
    Path(f)
    for f in FILES
    if Path(f).suffix in {".md", ".py", ".json", ".jsonl", ".yml", ".yaml", ".tf", ".hcl", ".bicep", ".txt", ".toml", ".sh"} and Path(f).exists()
]


def test_reference_pdf_is_never_committed():
    assert not [f for f in FILES if f.lower().endswith(".pdf")]


def test_cheat_sheet_credited_by_name():
    text = Path("README.md").read_text()
    assert "LangChain & LangGraph Cheat Sheet" in text and "AI Engineering Insider" in text


@pytest.mark.parametrize("path", MD, ids=str)
def test_doc_links_resolve(path):
    for target in re.findall(r"\]\(([^)#\s]+)(?:#[^)]*)?\)", path.read_text()):
        if target.startswith(("http://", "https://", "mailto:")):
            continue
        assert (path.parent / target).resolve().exists(), f"{path}: broken link {target}"


def test_no_dates_in_markdown():
    date = re.compile(r"\b20\d\d-\d\d-\d\d\b|\b(January|February|March|April|June|July|August|September|October|November|December) 20\d\d\b")
    assert not [str(p) for p in MD if date.search(p.read_text())]


def test_no_secrets_or_keys():
    pats = [re.compile(p) for p in (r"lsv2_(pt|sk)_[0-9a-f]{20,}", r"sk-[A-Za-z0-9]{20,}", r"AKIA[0-9A-Z]{16}", r"-----BEGIN [A-Z ]*PRIVATE KEY-----",
                                    r"AccountKey=[A-Za-z0-9+/=]{20,}")]  # fmt: skip
    hits = [str(p) for p in TEXT for pat in pats if pat.search(p.read_text(errors="ignore"))]
    assert not hits


def test_only_mock_guids_outside_role_definitions():
    guid = re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b")
    allowed_roles = {"7f951dda-4ed3-4680-a7ca-43fe172d538d", "4633458b-17de-408a-b874-0445c86b69e6"}  # AcrPull, Key Vault Secrets User
    for p in TEXT:
        for g in guid.findall(p.read_text(errors="ignore")):
            assert g.startswith("00000000-") or g in allowed_roles or g.startswith("6f1c2b8e-0000") or g.split("-")[2].startswith("5"), (
                f"{p}: {g}"
            )  # uuid5: derived, not an identifier


def test_companies_are_the_fictional_five():
    from lcstack.core import companies

    names = " ".join(str(v) for v in vars(companies).values() if isinstance(v, str))
    for n in ("Wrenfield", "Kestrel Ridge", "Halsey Vale", "Ferrowind", "Quillmere"):
        assert n in names


def test_readme_never_claims_deployment():
    text = Path("README.md").read_text().lower()
    assert "nothing has been deployed" in text
    assert not re.search(r"\b(is|was) deployed to\b|\blive at\b|\bin production at\b", text)


def test_readme_table_has_25_rows():
    rows = [line for line in Path("README.md").read_text().splitlines() if re.match(r"\| \d\d \|", line)]
    assert len(rows) == 25


def test_root_files_exist():
    for f in ("LICENSE", "SECURITY.md", "CONTRIBUTING.md", "CHANGELOG.md", ".env.example", "langgraph.json", "requirements.lock"):
        assert Path(f).exists(), f


def test_security_policy_has_a_fallback_contact():
    assert "Security contact request" in Path("SECURITY.md").read_text()


def test_six_adrs():
    assert len(list(Path("docs/adr").glob("0*.md"))) == 6
