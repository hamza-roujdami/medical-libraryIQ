import httpx
import pytest
import respx

from libraryiq.lookup import LookupFailed, PublicLookup

CROSSREF_WORK = {
    "message": {
        "DOI": "10.1000/DEMO.1",
        "title": ["A synthetic article about nothing"],
        "container-title": ["The Lancet"],
        "ISSN": ["0140-6736"],
        "issued": {"date-parts": [[2021, 5]]},
        "author": [{"given": "Ada", "family": "Lovelace"}, {"family": "Turing"}],
    }
}

PUBMED_SUMMARY = {
    "result": {
        "uids": ["111"],
        "111": {
            "title": "A synthetic PubMed article.",
            "fulljournalname": "JAMA",
            "issn": "0098-7484",
            "pubdate": "2019 Mar 5",
            "authors": [{"name": "Hopper G"}],
            "articleids": [
                {"idtype": "pubmed", "value": "111"},
                {"idtype": "doi", "value": "10.1000/PM.1"},
            ],
        },
    }
}


@pytest.fixture
async def lookup():
    async with httpx.AsyncClient() as client:
        yield PublicLookup(client, "test@example.org")


@respx.mock
async def test_by_doi_maps_crossref(lookup):
    respx.get("https://api.crossref.org/works/10.1000/demo.1").respond(json=CROSSREF_WORK)
    article = await lookup.by_doi("10.1000/demo.1")
    assert article is not None
    assert article.title == "A synthetic article about nothing"
    assert article.journal == "The Lancet"
    assert article.year == 2021
    assert article.authors == ["Ada Lovelace", "Turing"]
    assert article.doi == "10.1000/demo.1"
    assert article.source == "Crossref"


@respx.mock
async def test_by_doi_unknown_returns_none(lookup):
    respx.get("https://api.crossref.org/works/10.1000/missing").respond(404)
    assert await lookup.by_doi("10.1000/missing") is None


@respx.mock
async def test_by_pmid_maps_pubmed_and_extracts_doi(lookup):
    respx.get("https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi").respond(
        json=PUBMED_SUMMARY
    )
    article = await lookup.by_pmid("111")
    assert article is not None
    assert article.title == "A synthetic PubMed article"
    assert article.pmid == "111"
    assert article.doi == "10.1000/pm.1"
    assert article.year == 2019
    assert article.source == "PubMed"


@respx.mock
async def test_by_pmid_error_record_returns_none(lookup):
    respx.get("https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi").respond(
        json={"result": {"uids": [], "999": {"error": "cannot get document summary"}}}
    )
    assert await lookup.by_pmid("999") is None


@respx.mock
async def test_by_citation_returns_candidates(lookup):
    respx.get("https://api.crossref.org/works").respond(
        json={"message": {"items": [CROSSREF_WORK["message"]] * 2}}
    )
    candidates = await lookup.by_citation("Lovelace synthetic article", limit=3)
    assert len(candidates) == 2


@respx.mock
async def test_free_copy_prefers_pdf(lookup):
    respx.get("https://api.unpaywall.org/v2/10.1000/demo.1").respond(
        json={
            "is_oa": True,
            "best_oa_location": {
                "url": "https://x.org/landing",
                "url_for_pdf": "https://x.org/a.pdf",
                "version": "publishedVersion",
                "license": "cc-by",
            },
        }
    )
    copy = await lookup.free_copy("10.1000/demo.1")
    assert copy is not None
    assert copy.url == "https://x.org/a.pdf"
    assert copy.license == "cc-by"


@respx.mock
async def test_free_copy_none_when_closed(lookup):
    respx.get("https://api.unpaywall.org/v2/10.1000/demo.1").respond(
        json={"is_oa": False, "best_oa_location": None}
    )
    assert await lookup.free_copy("10.1000/demo.1") is None


@respx.mock
async def test_server_error_raises_lookup_failed(lookup):
    respx.get("https://api.crossref.org/works/10.1000/boom").respond(503)
    with pytest.raises(LookupFailed):
        await lookup.by_doi("10.1000/boom")


@respx.mock
async def test_network_error_raises_lookup_failed(lookup):
    respx.get("https://api.crossref.org/works/10.1000/down").mock(
        side_effect=httpx.ConnectError("down")
    )
    with pytest.raises(LookupFailed):
        await lookup.by_doi("10.1000/down")
