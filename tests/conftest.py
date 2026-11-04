import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from opsdesk.service import Desk, conectar  # noqa: E402


class Relogio:
    def __init__(self):
        self.t = datetime(2026, 11, 4, 12, 0, 0)

    def __call__(self):
        return self.t

    def avancar(self, **kw):
        self.t += timedelta(**kw)


@pytest.fixture
def relogio():
    return Relogio()


@pytest.fixture
def desk(relogio):
    return Desk(conectar(":memory:"), relogio=relogio)
