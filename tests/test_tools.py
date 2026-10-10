from fakes import FakeLookup, article
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


async def test_find_has_access_returns_link_and_sources(make_tools):
    tools = make_tools(FakeLookup(articles={"10.1000/a.1": article()}))
    result = await tools.find_article("10.1000/a.1")
    assert result["status"] == "has_access"
    assert result["article"]["source"] == "Crossref"
    assert "demo" in result["access"]["source"]
    assert result["link"] == result["access"]["links"][0]["url"]
    assert result["link"] in result["message"]
    assert "free_copy" not in result


async def test_find_falls_back_to_free_copy(make_tools):
    art = article(journal="Unlisted Journal")
    copy = FreeCopy(url="https://x.org/a.pdf")
    tools = make_tools(FakeLookup(articles={art.doi: art}, free_copies={art.doi: copy}))
    result = await tools.find_article(art.doi)
    assert result["status"] == "free_copy"
    assert result["link"] == "https://x.org/a.pdf"


async def test_find_needs_request_when_nothing_available(make_tools):
    art = article(journal="Unlisted Journal")
    result = await make_tools(FakeLookup(articles={art.doi: art})).find_article(art.doi)
    assert result["status"] == "needs_request"
    assert result["article"]["doi"] == art.doi


async def test_find_by_pmid(make_tools):
    art = article(doi=None, pmid="111")
    result = await make_tools(FakeLookup(articles={"111": art})).find_article("PMID: 111")
    assert result["status"] == "has_access"


async def test_find_typed_citation_returns_numbered_options_to_confirm(make_tools):
    candidates = [article(doi="10.1000/a.1"), article(doi="10.1000/a.2")]
    result = await make_tools(FakeLookup(citations=candidates)).find_article(
        "synthetic article lancet 2020"
    )
    assert result["status"] == "confirm_match"
    assert "access" not in result
    assert result["options"][0].startswith("1. Synthetic article")
    assert "10.1000/a.2" in result["options"][1]


async def test_find_not_found(make_tools):
    tools = make_tools()
    assert (await tools.find_article("10.1000/nope"))["status"] == "not_found"
    assert (await tools.find_article("some unknown citation"))["status"] == "not_found"


async def test_find_reports_a_lookup_outage_instead_of_raising(make_tools):
    class Down(FakeLookup):
        async def by_doi(self, doi):
            raise LookupFailed("api.crossref.org is unreachable")

    result = await make_tools(Down()).find_article("10.1000/a.1")
    assert result["status"] == "error"
    assert "try again" in result["message"]


async def test_request_needs_a_doi_or_pmid(make_tools, notifier):
    result = await make_tools().request_article(ALEX, "Smith 2020 some paper")
    assert result["status"] == "error"
    assert notifier.outbox == []


async def test_request_creates_pending_request_and_emails_librarian(make_tools, notifier):
    art = article(journal="Unlisted Journal")
    tools = make_tools(FakeLookup(articles={art.doi: art}))
    result = await tools.request_article(ALEX, art.doi, "for a journal club")
    assert result["status"] == "created"
    request = tools.store.get(result["request_id"])
    assert request.status == "pending"
    assert request.requester == ALEX.id
    assert request.note == "for a journal club"
    mail = notifier.outbox[0]
    assert mail.to == "librarian@example.org"
    assert f"/requests/{request.id}" in mail.body


async def test_duplicate_pending_request_is_not_created_twice(make_tools, notifier):
    art = article(journal="Unlisted Journal")
    tools = make_tools(FakeLookup(articles={art.doi: art}))
    first = await tools.request_article(ALEX, art.doi)
    second = await tools.request_article(ALEX, art.doi)
    assert second["status"] == "already_pending"
    assert second["request_id"] == first["request_id"]
    assert len(notifier.outbox) == 1


async def test_request_for_unknown_doi_creates_nothing(make_tools, notifier):
    result = await make_tools().request_article(ALEX, "10.1000/nope")
    assert result["status"] == "not_found"
    assert notifier.outbox == []


async def _pending(make_tools, notifier_unused=None):
    art = article(journal="Unlisted Journal")
    tools = make_tools(FakeLookup(articles={art.doi: art}))
    created = await tools.request_article(ALEX, art.doi, "journal club")
    return tools, created["request_id"]


async def test_same_article_by_a_different_requester_is_a_separate_request(make_tools):
    tools, first = await _pending(make_tools)
    second = await tools.request_article(BOB, "10.1000/a.1")
    assert second["status"] == "created"
    assert second["request_id"] != first


async def test_status_shows_the_requester_their_own_request(make_tools):
    tools, request_id = await _pending(make_tools)
    result = await tools.get_request_status(ALEX, request_id.lower())
    assert result["status"] == "pending"
    assert result["article"] == "Synthetic article"


async def test_a_requester_cannot_see_someone_elses_request(make_tools):
    tools, request_id = await _pending(make_tools)
    assert (await tools.get_request_status(BOB, request_id))["status"] == "not_found"
    assert (await tools.get_request_status(SAM, request_id))["status"] == "pending"


async def test_status_of_an_unknown_request(make_tools):
    assert (await make_tools().get_request_status(ALEX, "REQ-NOPE"))["status"] == "not_found"


async def test_only_the_librarian_can_list_pending_requests(make_tools):
    tools, request_id = await _pending(make_tools)
    assert (await tools.list_pending_requests(ALEX))["status"] == "forbidden"
    listed = await tools.list_pending_requests(SAM)
    assert listed["count"] == 1
    assert listed["requests"][0]["request_id"] == request_id
    assert listed["requests"][0]["requester"] == ALEX.id


async def test_only_the_librarian_can_decide(make_tools):
    tools, request_id = await _pending(make_tools)
    result = await tools.decide_request(ALEX, request_id, True)
    assert result["status"] == "forbidden"
    assert (await tools.get_request_status(ALEX, request_id))["status"] == "pending"


async def test_decision_updates_status_and_emails_requester(make_tools, notifier):
    tools, request_id = await _pending(make_tools)
    result = await tools.decide_request(SAM, request_id, False, "Held in print")
    assert result["status"] == "declined"
    assert result["decision_reason"] == "Held in print"
    assert notifier.outbox[-1].to == ALEX.id
    assert "declined" in notifier.outbox[-1].subject
    assert (await tools.get_request_status(ALEX, request_id))["status"] == "declined"


async def test_a_request_can_only_be_decided_once(make_tools):
    tools, request_id = await _pending(make_tools)
    assert (await tools.decide_request(SAM, request_id, True))["status"] == "approved"
    assert (await tools.decide_request(SAM, request_id, False))["status"] == "not_found"
    assert (await tools.decide_request(SAM, "REQ-NOPE", True))["status"] == "not_found"
