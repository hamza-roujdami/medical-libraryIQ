from fakes import FakeLookup, article
from libraryiq.core.access import SampleAccessChecker
from libraryiq.core.models import FreeCopy
from libraryiq.core.service import decide_request, find_article, request_article


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


async def test_find_has_access(make_services):
    svc = make_services(FakeLookup(articles={"10.1000/a.1": article()}))
    result = await find_article(svc, "10.1000/a.1")
    assert result.status == "has_access"
    assert result.access and result.access.links
    assert result.free_copy is None


async def test_find_falls_back_to_free_copy(make_services):
    art = article(journal="Unlisted Journal")
    copy = FreeCopy(url="https://x.org/a.pdf")
    svc = make_services(FakeLookup(articles={art.doi: art}, free_copies={art.doi: copy}))
    result = await find_article(svc, art.doi)
    assert result.status == "free_copy"
    assert result.free_copy == copy


async def test_find_needs_request_when_nothing_available(make_services):
    art = article(journal="Unlisted Journal")
    svc = make_services(FakeLookup(articles={art.doi: art}))
    result = await find_article(svc, art.doi)
    assert result.status == "needs_request"
    assert result.article == art


async def test_find_by_pmid(make_services):
    art = article(doi=None, pmid="111")
    svc = make_services(FakeLookup(articles={"111": art}))
    result = await find_article(svc, "PMID: 111")
    assert result.status == "has_access"


async def test_find_typed_citation_asks_to_confirm(make_services):
    candidates = [article(doi="10.1000/a.1"), article(doi="10.1000/a.2")]
    svc = make_services(FakeLookup(citations=candidates))
    result = await find_article(svc, "Smith 2020 synthetic article Lancet")
    assert result.status == "confirm_match"
    assert result.candidates == candidates
    assert result.access is None


async def test_find_not_found(make_services):
    svc = make_services(FakeLookup())
    assert (await find_article(svc, "10.1000/nope")).status == "not_found"
    assert (await find_article(svc, "some unknown citation")).status == "not_found"


async def test_request_creates_pending_request_and_emails_librarian(make_services, notifier):
    art = article(journal="Unlisted Journal")
    svc = make_services(FakeLookup(articles={art.doi: art}))
    request, created = await request_article(svc, art.doi, "for a journal club")
    assert created
    assert request.status == "pending"
    assert request.requester == "staff@example.org"
    assert request.note == "for a journal club"
    assert len(notifier.outbox) == 1
    mail = notifier.outbox[0]
    assert mail.to == "librarian@example.org"
    assert f"/requests/{request.id}" in mail.body


async def test_duplicate_pending_request_is_not_created_twice(make_services, notifier):
    art = article(journal="Unlisted Journal")
    svc = make_services(FakeLookup(articles={art.doi: art}))
    first, _ = await request_article(svc, art.doi, None)
    second, created = await request_article(svc, art.doi, None)
    assert not created
    assert second.id == first.id
    assert len(notifier.outbox) == 1


async def test_request_for_unknown_article_or_citation_creates_nothing(make_services, notifier):
    svc = make_services(FakeLookup())
    assert await request_article(svc, "10.1000/nope", None) == (None, False)
    assert await request_article(svc, "just a citation", None) == (None, False)
    assert notifier.outbox == []


async def test_decision_updates_status_and_emails_requester(make_services, notifier):
    art = article(journal="Unlisted Journal")
    svc = make_services(FakeLookup(articles={art.doi: art}))
    request, _ = await request_article(svc, art.doi, None)
    decided = await decide_request(svc, request.id, approved=False, reason="Already held in print")
    assert decided.status == "declined"
    assert decided.decision_reason == "Already held in print"
    assert notifier.outbox[-1].to == "staff@example.org"
    assert "declined" in notifier.outbox[-1].subject


async def test_a_request_can_only_be_decided_once(make_services):
    art = article(journal="Unlisted Journal")
    svc = make_services(FakeLookup(articles={art.doi: art}))
    request, _ = await request_article(svc, art.doi, None)
    assert await decide_request(svc, request.id, True, None) is not None
    assert await decide_request(svc, request.id, False, None) is None
    assert await decide_request(svc, "REQ-NOPE", True, None) is None
