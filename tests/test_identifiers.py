import pytest

from libraryiq.core.identifiers import Identifier, parse_identifier


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("10.1038/nature12373", Identifier("doi", "10.1038/nature12373")),
        ("doi:10.1056/NEJMoa2034577", Identifier("doi", "10.1056/nejmoa2034577")),
        ("https://doi.org/10.1000/xyz123.", Identifier("doi", "10.1000/xyz123")),
        (
            "Please find (10.1016/S0140-6736(20)30183-5).",
            Identifier("doi", "10.1016/s0140-6736(20)30183-5"),
        ),
        ("PMID: 23868258", Identifier("pmid", "23868258")),
        ("pmid 23868258", Identifier("pmid", "23868258")),
        ("https://pubmed.ncbi.nlm.nih.gov/23868258/", Identifier("pmid", "23868258")),
        ("23868258", Identifier("pmid", "23868258")),
    ],
)
def test_parses_identifiers(text, expected):
    assert parse_identifier(text) == expected


@pytest.mark.parametrize("text", ["Smith J. Heart failure outcomes. JAMA 2019", "1234", "hello"])
def test_free_text_is_a_citation(text):
    ident = parse_identifier(text)
    assert ident.kind == "citation"
    assert ident.value == text
