from __future__ import annotations

from typing import Any, Protocol
from urllib.parse import quote

import httpx

from libraryiq.core.models import Article, FreeCopy

CROSSREF = "https://api.crossref.org"
EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
UNPAYWALL = "https://api.unpaywall.org/v2"


class LookupFailed(Exception):
    """A public lookup service could not be reached or returned an error."""


class ArticleLookup(Protocol):
    async def by_doi(self, doi: str) -> Article | None: ...

    async def by_pmid(self, pmid: str) -> Article | None: ...

    async def by_citation(self, text: str, limit: int = 3) -> list[Article]: ...

    async def free_copy(self, doi: str) -> FreeCopy | None: ...


def make_http_client(contact_email: str) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        timeout=httpx.Timeout(10.0),
        headers={"User-Agent": f"LibraryIQ/0.1 (mailto:{contact_email})"},
        follow_redirects=True,
    )


class PublicLookup:
    """Crossref, PubMed and Unpaywall. Only a DOI, PubMed ID or title is ever sent."""

    def __init__(self, client: httpx.AsyncClient, contact_email: str) -> None:
        self._client = client
        self._email = contact_email

    async def _get_json(self, url: str, params: dict[str, Any]) -> dict[str, Any] | None:
        try:
            response = await self._client.get(url, params=params)
        except httpx.HTTPError as exc:
            raise LookupFailed(f"{httpx.URL(url).host} is unreachable") from exc
        if response.status_code == 404:
            return None
        if response.is_error:
            raise LookupFailed(f"{httpx.URL(url).host} returned HTTP {response.status_code}")
        try:
            return response.json()
        except ValueError as exc:
            raise LookupFailed(f"{httpx.URL(url).host} returned invalid JSON") from exc

    async def by_doi(self, doi: str) -> Article | None:
        data = await self._get_json(
            f"{CROSSREF}/works/{quote(doi, safe='/')}", {"mailto": self._email}
        )
        if not data or "message" not in data:
            return None
        return _from_crossref(data["message"])

    async def by_citation(self, text: str, limit: int = 3) -> list[Article]:
        data = await self._get_json(
            f"{CROSSREF}/works",
            {"query.bibliographic": text, "rows": limit, "mailto": self._email},
        )
        items = (data or {}).get("message", {}).get("items", [])
        return [_from_crossref(item) for item in items[:limit]]

    async def by_pmid(self, pmid: str) -> Article | None:
        data = await self._get_json(
            f"{EUTILS}/esummary.fcgi",
            {
                "db": "pubmed",
                "id": pmid,
                "retmode": "json",
                "tool": "libraryiq",
                "email": self._email,
            },
        )
        record = ((data or {}).get("result") or {}).get(pmid)
        if not record or "error" in record:
            return None
        return _from_pubmed(pmid, record)

    async def free_copy(self, doi: str) -> FreeCopy | None:
        data = await self._get_json(f"{UNPAYWALL}/{quote(doi, safe='/')}", {"email": self._email})
        location = (data or {}).get("best_oa_location")
        if not data or not data.get("is_oa") or not location:
            return None
        url = location.get("url_for_pdf") or location.get("url")
        if not url:
            return None
        return FreeCopy(url=url, version=location.get("version"), license=location.get("license"))


def _from_crossref(item: dict[str, Any]) -> Article:
    year_parts = (item.get("issued") or {}).get("date-parts") or [[None]]
    authors = [
        " ".join(p for p in (a.get("given"), a.get("family")) if p) for a in item.get("author", [])
    ]
    return Article(
        title=(item.get("title") or ["(no title)"])[0],
        journal=(item.get("container-title") or [None])[0],
        issn=item.get("ISSN", []),
        year=year_parts[0][0] if year_parts and year_parts[0] else None,
        authors=authors[:10],
        doi=(item.get("DOI") or "").lower() or None,
        source="Crossref",
    )


def _from_pubmed(pmid: str, record: dict[str, Any]) -> Article:
    doi = next((i["value"] for i in record.get("articleids", []) if i.get("idtype") == "doi"), None)
    pubdate = record.get("pubdate") or ""
    year = int(pubdate[:4]) if pubdate[:4].isdigit() else None
    return Article(
        title=(record.get("title") or "(no title)").rstrip("."),
        journal=record.get("fulljournalname") or record.get("source"),
        issn=[i for i in (record.get("issn"), record.get("essn")) if i],
        year=year,
        authors=[a["name"] for a in record.get("authors", []) if a.get("name")][:10],
        doi=doi.lower() if doi else None,
        pmid=pmid,
        source="PubMed",
    )
