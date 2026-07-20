from __future__ import annotations

import subprocess

import pytest

from vaultgfs import catalog
from vaultgfs.pfsense_backup import PfSenseClient, first_form, run_pfsense_job, validate_pfsense_xml


def test_first_form_extracts_csrf_and_login_fields():
    form = first_form(
        """
        <html><form action="/">
          <input type="hidden" name="__csrf_magic" value="token">
          <input name="usernamefld">
          <input name="passwordfld">
        </form></html>
        """
    )

    assert [item.get("name") for item in form["inputs"]] == ["__csrf_magic", "usernamefld", "passwordfld"]


def test_validate_pfsense_xml_rejects_non_pfsense_xml():
    with pytest.raises(RuntimeError, match="unexpected root"):
        validate_pfsense_xml(b"<notpfsense />")


def test_client_download_posts_csrf_and_validates_xml():
    requests = []

    class FakeResponse:
        def __init__(self, body):
            self.body = body

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def read(self):
            return self.body

    client = PfSenseClient("https://example", "user", "pass", verify_tls=False)

    def fake_request(path, data=None):
        requests.append((path, data))
        if path == "/diag_backup.php" and data is None:
            return FakeResponse(b'<form><input name="__csrf_magic" value="csrf"></form>')
        return FakeResponse(b"<pfsense><system /></pfsense>")

    client.request = fake_request

    body = client.download_config(include_rrd=False)

    assert body == b"<pfsense><system /></pfsense>"
    assert requests[-1][1]["__csrf_magic"] == "csrf"
    assert requests[-1][1]["donotbackuprrd"] == "yes"


def test_run_pfsense_job_catalogs_compressed_artifact(monkeypatch, tmp_path):
    db_path = tmp_path / "catalog.db"
    dest = tmp_path / "pfsense"

    class FakeClient:
        def __init__(self, *args):
            pass

        def login(self):
            pass

        def download_config(self, include_rrd):
            return b"<pfsense><system /></pfsense>"

    def fake_run(cmd, input=None, stdout=None, stderr=None, check=None):
        output = cmd[cmd.index("-o") + 1]
        with open(output, "wb") as f:
            f.write(input)
        return subprocess.CompletedProcess(cmd, 0, stderr=b"")

    monkeypatch.setattr("vaultgfs.pfsense_backup.PfSenseClient", FakeClient)
    monkeypatch.setattr("vaultgfs.pfsense_backup.subprocess.run", fake_run)

    rc = run_pfsense_job(
        {"defaults": {"catalog": str(db_path)}},
        {
            "name": "pfsense",
            "type": "pfsense-config",
            "base_url": "https://example",
            "username": "user",
            "password": "secret",
            "verify_tls": False,
            "destination": str(dest),
        },
    )

    db = catalog.connect(db_path)
    artifact = db.execute("select path, kind from backup_artifacts").fetchone()

    assert rc == 0
    assert artifact["kind"] == "pfsense-config"
    assert artifact["path"].endswith(".xml.zst")
