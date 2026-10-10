from __future__ import annotations

import re

from pydantic import BaseModel, Field

from libraryiq.lookup import Article

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


class AccessLink(BaseModel):
    category: str
    text: str
    url: str


class AccessResult(BaseModel):
    subscribed: bool
    links: list[AccessLink] = Field(default_factory=list)
    source: str


def _normalise(title: str) -> str:
    return re.sub(r"[^a-z0-9 ]", "", title.lower()).removeprefix("the ").strip()


class SampleAccessChecker:
    """Stand-in for the library's link resolver, returning links with a category and a URL.

    Replace with a client for the real service; it only needs the same `check` method.
    """

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
