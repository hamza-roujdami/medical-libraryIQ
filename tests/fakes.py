from libraryiq.lookup import Article


class FakeLookup:
    def __init__(self, articles=None, citations=None, free_copies=None):
        self.articles = articles or {}
        self.citations = citations or []
        self.free_copies = free_copies or {}

    async def by_doi(self, doi):
        return self.articles.get(doi)

    async def by_pmid(self, pmid):
        return self.articles.get(pmid)

    async def by_citation(self, text, limit=3):
        return self.citations[:limit]

    async def free_copy(self, doi):
        return self.free_copies.get(doi)


def article(doi="10.1000/a.1", journal="The Lancet", pmid=None, title="Synthetic article"):
    return Article(title=title, journal=journal, year=2020, doi=doi, pmid=pmid, source="Crossref")
