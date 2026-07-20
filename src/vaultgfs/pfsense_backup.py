from __future__ import annotations

from html.parser import HTMLParser
import http.cookiejar
from pathlib import Path
import ssl
import subprocess
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

from . import catalog


class FormParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.forms = []
        self.current = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "form":
            self.current = {"action": attrs.get("action", ""), "inputs": []}
        elif self.current is not None and tag in {"input", "button"}:
            self.current["inputs"].append(attrs)

    def handle_endtag(self, tag):
        if tag == "form" and self.current is not None:
            self.forms.append(self.current)
            self.current = None


def first_form(html: str) -> dict:
    parser = FormParser()
    parser.feed(html)
    if not parser.forms:
        raise RuntimeError("pfSense page did not contain an HTML form")
    return parser.forms[0]


def form_values(form: dict) -> dict[str, str]:
    values = {}
    for item in form["inputs"]:
        name = item.get("name")
        if name:
            values[name] = item.get("value", "")
    return values


class PfSenseClient:
    def __init__(self, base_url: str, username: str, password: str, verify_tls: bool = True):
        self.base_url = base_url.rstrip("/")
        self.username = username
        self.password = password
        ctx = ssl.create_default_context() if verify_tls else ssl._create_unverified_context()
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPSHandler(context=ctx),
            urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()),
        )

    def request(self, path: str, data: dict[str, str] | None = None):
        body = urllib.parse.urlencode(data).encode() if data is not None else None
        headers = {"User-Agent": "vaultGFS-pfsense/1.0"}
        if body is not None:
            headers["Content-Type"] = "application/x-www-form-urlencoded"
        req = urllib.request.Request(f"{self.base_url}/{path.lstrip('/')}", data=body, headers=headers)
        return self.opener.open(req, timeout=30)

    def get_text(self, path: str) -> str:
        with self.request(path) as response:
            return response.read().decode("utf-8", errors="replace")

    def login(self):
        html = self.get_text("/")
        values = form_values(first_form(html))
        values["usernamefld"] = self.username
        values["passwordfld"] = self.password
        with self.request("/", values) as response:
            html = response.read().decode("utf-8", errors="replace")
        if "usernamefld" in html and "passwordfld" in html:
            raise RuntimeError("pfSense login failed")

    def download_config(self, include_rrd: bool = False) -> bytes:
        html = self.get_text("/diag_backup.php")
        values = form_values(first_form(html))
        csrf = values.get("__csrf_magic")
        if not csrf:
            raise RuntimeError("pfSense backup form did not include CSRF token")
        post = {
            "__csrf_magic": csrf,
            "backuparea": "",
            "download": "Download configuration as XML",
        }
        if not include_rrd:
            post["donotbackuprrd"] = "yes"
        with self.request("/diag_backup.php", post) as response:
            body = response.read()
        validate_pfsense_xml(body)
        return body


def validate_pfsense_xml(body: bytes):
    try:
        root = ET.fromstring(body)
    except ET.ParseError as exc:
        raise RuntimeError("pfSense backup response was not valid XML") from exc
    if root.tag != "pfsense":
        raise RuntimeError(f"pfSense backup XML has unexpected root: {root.tag}")
    if root.find("system") is None:
        raise RuntimeError("pfSense backup XML does not include system section")


def run_pfsense_job(cfg, job):
    defaults = cfg.get("defaults", {})
    db = catalog.connect(defaults.get("catalog", "/var/lib/vaultgfs/catalog.db"))
    run_id = catalog.start_run(db, job, "config")
    dest = Path(job["destination"])
    dest.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y%m%d-%H%M%S")
    out = dest / f"{job['name']}-{ts}.xml.zst"
    try:
        client = PfSenseClient(
            job["base_url"],
            job["username"],
            job["password"],
            bool(job.get("verify_tls", True)),
        )
        client.login()
        xml = client.download_config(bool(job.get("include_rrd", False)))
        level = int(job.get("compression_level", defaults.get("compression_level", 19)))
        threads = int(job.get("compression_threads", defaults.get("compression_threads", 1)))
        if threads < 1:
            threads = 1
        cmd = ["zstd", f"-T{threads}", "-o", str(out), f"-{level}"]
        if level > 19:
            cmd.append("--ultra")
        proc = subprocess.run(cmd, input=xml, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, check=False)
        if proc.returncode != 0:
            raise RuntimeError(f"zstd failed for pfSense config: {proc.stderr.decode(errors='replace')}")
        catalog.insert_artifacts(db, run_id, [out], "pfsense-config")
        catalog.finish_run(db, run_id, "success", str(dest), None, "downloaded pfSense XML config")
        print(f"SUCCESS {job['name']}: pfSense XML config -> {out}")
        return 0
    except BaseException as exc:
        try:
            out.unlink(missing_ok=True)
        except FileNotFoundError:
            pass
        catalog.finish_run(db, run_id, "failed", str(dest), None, str(exc))
        raise
