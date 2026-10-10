from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

_DOI = re.compile(r"(10\.\d{4,9}/[^\s\"<>]+)", re.IGNORECASE)
_PMID_LABELLED = re.compile(r"\bpmid\s*[:#]?\s*(\d{1,9})\b", re.IGNORECASE)
_PUBMED_URL = re.compile(r"pubmed\.ncbi\.nlm\.nih\.gov/(\d{1,9})", re.IGNORECASE)
_PMID_BARE = re.compile(r"^\d{5,9}$")
_TRAILING = ".,;:!?]}>\"'"


@dataclass(frozen=True)
class Identifier:
    kind: Literal["doi", "pmid", "citation"]
    value: str


def clean_doi(raw: str) -> str:
    doi = raw.strip().rstrip(_TRAILING)
    while doi.endswith(")") and doi.count("(") < doi.count(")"):
        doi = doi[:-1].rstrip(_TRAILING)
    return doi.lower()


def parse_identifier(text: str) -> Identifier:
    """Classify user input as a DOI, a PubMed ID or a free-text citation."""
    s = text.strip()
    if m := _DOI.search(s):
        return Identifier("doi", clean_doi(m.group(1)))
    if m := _PMID_LABELLED.search(s) or _PUBMED_URL.search(s):
        return Identifier("pmid", m.group(1))
    if _PMID_BARE.match(s):
        return Identifier("pmid", s)
    return Identifier("citation", s)
