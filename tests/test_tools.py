from fakes import FakeLookup, article
from libraryiq.core.lookup import LookupFailed
from libraryiq.tools import make_tools


def tools_by_name(svc):
    return {t.name: t for t in make_tools(svc)}


async def call(tools, name, **arguments):
    return await tools[name].invoke(arguments=arguments, skip_parsing=True)


def test_exposes_exactly_the_two_tools(make_services):
    assert set(tools_by_name(make_services(FakeLookup()))) == {"find_article", "request_article"}


async def test_find_returns_status_and_sources(make_services):
    svc = make_services(FakeLookup(articles={"10.1000/a.1": article()}))
    result = await call(tools_by_name(svc), "find_article", query="10.1000/a.1")
    assert result["status"] == "has_access"
    assert result["article"]["source"] == "Crossref"
    assert "demo" in result["access"]["source"]


async def test_find_citation_returns_numbered_options_without_raw_candidates(make_services):
    svc = make_services(
        FakeLookup(citations=[article(doi="10.1000/a.1"), article(doi="10.1000/a.2")])
    )
    result = await call(tools_by_name(svc), "find_article", query="synthetic article lancet 2020")
    assert result["status"] == "confirm_match"
    assert "candidates" not in result
    assert result["options"][0].startswith("1. Synthetic article")
    assert "10.1000/a.2" in result["options"][1]


async def test_find_reports_a_lookup_outage_instead_of_raising(make_services):
    class Down(FakeLookup):
        async def by_doi(self, doi):
            raise LookupFailed("api.crossref.org is unreachable")

    result = await call(tools_by_name(make_services(Down())), "find_article", query="10.1000/a.1")
    assert result["status"] == "error"
    assert "try again" in result["message"]


async def test_request_needs_a_doi_or_pmid(make_services, notifier):
    tools = tools_by_name(make_services(FakeLookup()))
    result = await call(tools, "request_article", identifier="Smith 2020 some paper")
    assert result["status"] == "error"
    assert notifier.outbox == []


async def test_request_creates_then_reports_duplicate(make_services, notifier):
    art = article(journal="Unlisted Journal")
    tools = tools_by_name(make_services(FakeLookup(articles={art.doi: art})))
    first = await call(tools, "request_article", identifier=art.doi, note="journal club")
    assert first["status"] == "created"
    assert first["request_id"].startswith("REQ-")
    second = await call(tools, "request_article", identifier=art.doi)
    assert second["status"] == "already_pending"
    assert second["request_id"] == first["request_id"]
    assert len(notifier.outbox) == 1


async def test_request_for_unknown_doi_is_not_found(make_services):
    tools = tools_by_name(make_services(FakeLookup()))
    assert (await call(tools, "request_article", identifier="10.1000/nope"))[
        "status"
    ] == "not_found"
