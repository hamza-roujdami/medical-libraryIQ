import pytest

from fakes import FakeLookup
from libraryiq.access import SampleAccessChecker
from libraryiq.orders import SimulatedNotifier, SqliteRequestStore
from libraryiq.tools import LibraryTools


@pytest.fixture
def notifier():
    return SimulatedNotifier()


@pytest.fixture
def make_tools(tmp_path, notifier):
    def _make(lookup=None):
        return LibraryTools(
            lookup or FakeLookup(),
            SampleAccessChecker(),
            SqliteRequestStore(tmp_path / "test.db"),
            notifier,
            librarian_email="librarian@example.org",
            approval_base_url="http://localhost:8000",
        )

    return _make
