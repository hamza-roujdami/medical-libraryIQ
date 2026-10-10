import pytest

from fakes import FakeLookup
from libraryiq.access import SampleAccessChecker
from libraryiq.orders import SimulatedNotifier, SqliteRequestStore
from libraryiq.tools import Library


@pytest.fixture
def notifier():
    return SimulatedNotifier()


@pytest.fixture
def make_library(tmp_path, notifier):
    def _make(lookup=None):
        return Library(
            lookup=lookup or FakeLookup(),
            access=SampleAccessChecker(),
            store=SqliteRequestStore(tmp_path / "test.db"),
            notifier=notifier,
            librarian_email="librarian@example.org",
        )

    return _make
