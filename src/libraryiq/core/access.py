from __future__ import annotations

import re
from typing import Protocol

from libraryiq.core.models import AccessLink, AccessResult, Article

SAMPLE_SOURCE = "Sample access list (demo, not a real subscription)"

# Synthetic stand-in for the library's subscription records.
SAMPLE_SUBSCRIBED_JOURNALS = (
    "New England Journal of Medicine",
    "The Lancet",
    "JAMA",
    "Nature Medicine",
    "BMJ",
    "Journal of the American College of Cardiology",
)


class AccessChecker(Protocol):
    async def check(self, article: Article) -> AccessResult: ...


def _normalise(title: str) -> str:
    return re.sub(r"[^a-z0-9 ]", "", title.lower()).removeprefix("the ").strip()


class SampleAccessChecker:
    """Returns data in the shape of a link resolver response: links with a category and a URL."""

    def __init__(self, journals: tuple[str, ...] = SAMPLE_SUBSCRIBED_JOURNALS) -> None:
        self._journals = {_normalise(j) for j in journals}

    async def check(self, article: Article) -> AccessResult:
        if article.journal and _normalise(article.journal) in self._journals:
            ref = article.doi or article.pmid or article.title
            return AccessResult(
                subscribed=True,
                links=[
                    AccessLink(
                        category="FullText",
                        text=f"Full text via {article.journal}",
                        url=f"https://library.example.org/fulltext?id={ref}",
                    )
                ],
                source=SAMPLE_SOURCE,
            )
        return AccessResult(subscribed=False, source=SAMPLE_SOURCE)
