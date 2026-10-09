import pytest

from libraryiq.core.access import SampleAccessChecker
from libraryiq.core.notify import SimulatedNotifier
from libraryiq.core.service import Services
from libraryiq.core.store import SqliteRequestStore


@pytest.fixture
def notifier():
    return SimulatedNotifier()


@pytest.fixture
def make_services(tmp_path, notifier):
    def _make(lookup):
        return Services(
            lookup=lookup,
            access=SampleAccessChecker(),
            store=SqliteRequestStore(tmp_path / "test.db"),
            notifier=notifier,
            librarian_email="librarian@example.org",
            approval_base_url="http://localhost:8000",
            requester="staff@example.org",
        )

    return _make
