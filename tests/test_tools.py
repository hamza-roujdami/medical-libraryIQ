from fakes import FakeLookup, article, call, tools_for
from libraryiq.access import SampleAccessChecker
from libraryiq.lookup import FreeCopy, LookupFailed
from libraryiq.tools import User

ALEX = User("alex.requester@example.org")
BOB = User("bob.requester@example.org")
SAM = User("sam.librarian@example.org", "librarian")


async def test_sample_checker_matches_journal_ignoring_case_and_leading_the():
    checker = SampleAccessChecker()
    assert (await checker.check(article(journal="the lancet"))).subscribed
    assert (await checker.check(article(journal="JAMA"))).subscribed
    assert not (await checker.check(article(journal="Some Unlisted Journal"))).subscribed
    assert not (await checker.check(article(journal=None))).subscribed


async def test_sample_checker_returns_link_shaped_result():
    result = await SampleAccessChecker().check(article(journal="The Lancet"))
    assert result.links[0].category == "FullText"
    assert result.links[0].url.startswith("https://library.example.org/")
    assert "demo" in result.source


def test_each_role_gets_only_its_own_tools(make_library):
    library = make_library()
    assert set(tools_for(library, ALEX)) == {
        "find_article",
        "request_article",
        "get_request_status",
    }
    assert set(tools_for(library, SAM)) == {
        "find_article",
        "list_pending_requests",
        "get_request_status",
        "decide_request",
    }


def test_only_the_decision_needs_the_librarians_confirmation(make_library):
    tools = tools_for(make_library(), SAM)
    needs = {name for name, t in tools.items() if t.approval_mode == "always_require"}
    assert needs == {"decide_request"}
    assert all(t.approval_mode == "never_require" for t in tools_for(make_library(), ALEX).values())


def test_tool_schemas_expose_only_what_the_model_chooses(make_library):
    tools = tools_for(make_library(), ALEX)
    request = tools["request_article"].parameters()
    assert request["required"] == ["identifier"]
    assert set(request["properties"]) == {"identifier", "note"}
    assert "DOI" in tools["find_article"].parameters()["properties"]["query"]["description"]


async def test_find_has_access_returns_link_and_sources(make_library):
    library = make_library(FakeLookup(articles={"10.1000/a.1": article()}))
    result = await call(library, ALEX, "find_article", query="10.1000/a.1")
    assert result["status"] == "has_access"
    assert result["article"]["source"] == "Crossref"
    assert "demo" in result["access"]["source"]
    assert result["link"] == result["access"]["links"][0]["url"]
    assert result["link"] in result["message"]
    assert "free_copy" not in result


async def test_find_falls_back_to_free_copy(make_library):
    art = article(journal="Unlisted Journal")
    copy = FreeCopy(url="https://x.org/a.pdf")
    library = make_library(FakeLookup(articles={art.doi: art}, free_copies={art.doi: copy}))
    result = await call(library, ALEX, "find_article", query=art.doi)
    assert result["status"] == "free_copy"
    assert result["link"] == "https://x.org/a.pdf"


async def test_find_needs_request_when_nothing_available(make_library):
    art = article(journal="Unlisted Journal")
    library = make_library(FakeLookup(articles={art.doi: art}))
    result = await call(library, ALEX, "find_article", query=art.doi)
    assert result["status"] == "needs_request"
    assert result["article"]["doi"] == art.doi


async def test_find_by_pmid(make_library):
    art = article(doi=None, pmid="111")
    library = make_library(FakeLookup(articles={"111": art}))
    result = await call(library, ALEX, "find_article", query="PMID: 111")
    assert result["status"] == "has_access"


async def test_find_typed_citation_returns_numbered_options_to_confirm(make_library):
    candidates = [article(doi="10.1000/a.1"), article(doi="10.1000/a.2")]
    library = make_library(FakeLookup(citations=candidates))
    result = await call(library, ALEX, "find_article", query="synthetic article lancet 2020")
    assert result["status"] == "confirm_match"
    assert "access" not in result
    assert result["options"][0].startswith("1. Synthetic article")
    assert "10.1000/a.2" in result["options"][1]


async def test_find_not_found(make_library):
    library = make_library()
    assert (await call(library, ALEX, "find_article", query="10.1000/nope"))[
        "status"
    ] == "not_found"
    unknown = await call(library, ALEX, "find_article", query="some unknown citation")
    assert unknown["status"] == "not_found"


async def test_find_reports_a_lookup_outage_instead_of_raising(make_library):
    class Down(FakeLookup):
        async def by_doi(self, doi):
            raise LookupFailed("api.crossref.org is unreachable")

    result = await call(make_library(Down()), ALEX, "find_article", query="10.1000/a.1")
    assert result["status"] == "error"
    assert "try again" in result["message"]


async def test_request_needs_a_doi_or_pmid(make_library, notifier):
    result = await call(make_library(), ALEX, "request_article", identifier="Smith 2020 some paper")
    assert result["status"] == "error"
    assert notifier.outbox == []


async def test_request_creates_pending_request_and_emails_librarian(make_library, notifier):
    art = article(journal="Unlisted Journal")
    library = make_library(FakeLookup(articles={art.doi: art}))
    result = await call(
        library, ALEX, "request_article", identifier=art.doi, note="for a journal club"
    )
    assert result["status"] == "created"
    request = library.store.get(result["request_id"])
    assert request.status == "pending"
    assert request.requester == ALEX.id
    assert request.note == "for a journal club"
    mail = notifier.outbox[0]
    assert mail.to == "librarian@example.org"
    assert request.id in mail.subject


async def test_duplicate_pending_request_is_not_created_twice(make_library, notifier):
    art = article(journal="Unlisted Journal")
    library = make_library(FakeLookup(articles={art.doi: art}))
    first = await call(library, ALEX, "request_article", identifier=art.doi)
    second = await call(library, ALEX, "request_article", identifier=art.doi)
    assert second["status"] == "already_pending"
    assert second["request_id"] == first["request_id"]
    assert len(notifier.outbox) == 1


async def test_request_for_unknown_doi_creates_nothing(make_library, notifier):
    result = await call(make_library(), ALEX, "request_article", identifier="10.1000/nope")
    assert result["status"] == "not_found"
    assert notifier.outbox == []


async def _pending(make_library):
    art = article(journal="Unlisted Journal")
    library = make_library(FakeLookup(articles={art.doi: art}))
    created = await call(library, ALEX, "request_article", identifier=art.doi, note="journal club")
    return library, created["request_id"]


async def test_same_article_by_a_different_requester_is_a_separate_request(make_library):
    library, first = await _pending(make_library)
    second = await call(library, BOB, "request_article", identifier="10.1000/a.1")
    assert second["status"] == "created"
    assert second["request_id"] != first


async def test_status_shows_the_requester_their_own_request(make_library):
    library, request_id = await _pending(make_library)
    result = await call(library, ALEX, "get_request_status", request_id=request_id.lower())
    assert result["status"] == "pending"
    assert result["article"] == "Synthetic article"


async def test_a_requester_cannot_see_someone_elses_request(make_library):
    library, request_id = await _pending(make_library)
    other = await call(library, BOB, "get_request_status", request_id=request_id)
    assert other["status"] == "not_found"
    librarian = await call(library, SAM, "get_request_status", request_id=request_id)
    assert librarian["status"] == "pending"


async def test_status_of_an_unknown_request(make_library):
    result = await call(make_library(), ALEX, "get_request_status", request_id="REQ-NOPE")
    assert result["status"] == "not_found"


async def test_the_librarian_lists_pending_requests(make_library):
    library, request_id = await _pending(make_library)
    listed = await call(library, SAM, "list_pending_requests")
    assert listed["count"] == 1
    assert listed["requests"][0]["request_id"] == request_id
    assert listed["requests"][0]["requester"] == ALEX.id


async def test_decision_updates_status_and_emails_requester(make_library, notifier):
    library, request_id = await _pending(make_library)
    result = await call(
        library,
        SAM,
        "decide_request",
        request_id=request_id,
        approved=False,
        reason="Held in print",
    )
    assert result["status"] == "declined"
    assert result["decision_reason"] == "Held in print"
    assert notifier.outbox[-1].to == ALEX.id
    assert "declined" in notifier.outbox[-1].subject
    seen = await call(library, ALEX, "get_request_status", request_id=request_id)
    assert seen["status"] == "declined"


async def test_a_request_can_only_be_decided_once(make_library):
    library, request_id = await _pending(make_library)
    approve = await call(library, SAM, "decide_request", request_id=request_id, approved=True)
    assert approve["status"] == "approved"
    again = await call(library, SAM, "decide_request", request_id=request_id, approved=False)
    assert again["status"] == "not_found"
    unknown = await call(library, SAM, "decide_request", request_id="REQ-NOPE", approved=True)
    assert unknown["status"] == "not_found"
