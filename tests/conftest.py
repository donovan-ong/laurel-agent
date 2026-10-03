import shutil
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


@pytest.fixture
def data_copy(tmp_path, monkeypatch):
    """A temporary copy of the data files that the tools read, so a test can change them."""
    from tools import common
    for f in common.DATA_DIR.glob("*.json"):
        shutil.copy(f, tmp_path / f.name)
    monkeypatch.setattr(common, "DATA_DIR", tmp_path)
    return tmp_path


@pytest.fixture(autouse=True)
def no_service_configured(tmp_path_factory, monkeypatch):
    """Tests use the local logic unless one sets a service up, whatever is in tools/service_config.json."""
    from tools import enrolment_client
    monkeypatch.setattr(enrolment_client, "CONFIG_PATH", tmp_path_factory.mktemp("noservice") / "service_config.json")
