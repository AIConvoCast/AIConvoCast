"""Check live domain certificates, HTTPS redirects, and scheduled site freshness."""

from datetime import datetime, timezone
import json
import os
import socket
import ssl
from urllib.parse import urlsplit
from urllib.request import Request, urlopen
from urllib.error import HTTPError


def enable_https_when_ready():
    """Only strengthen HTTPS, using the existing Pages workflow permission."""
    repository = os.environ["GITHUB_REPOSITORY"]
    if repository.lower() != "aiconvocast/aiconvocast":
        raise RuntimeError("HTTPS configuration is restricted to the AIConvoCast repository")
    url = f"https://api.github.com/repos/{repository}/pages"
    headers = {"Authorization": "Bearer " + os.environ["GITHUB_TOKEN"],
               "Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
    with urlopen(Request(url, headers=headers), timeout=30) as response:
        settings = json.load(response)
    if settings.get("cname") != "aiconvocast.com":
        raise RuntimeError("Pages custom domain changed; check hosting settings")
    if settings.get("https_enforced"):
        print("HTTPS enforcement is already enabled.")
        return True
    certificate = settings.get("https_certificate") or {}
    if certificate.get("state") not in {"approved", "issued"}:
        print("::warning::GitHub is still provisioning the domain certificate. Its Pages settings may require up to 24 hours. HTTPS is not yet enforced.")
        return False
    request = Request(url, headers={**headers, "Content-Type": "application/json"},
                      data=b'{"https_enforced": true}', method="PUT")
    try:
        with urlopen(request, timeout=30):
            pass
    except HTTPError as exc:
        detail = json.loads(exc.read()).get("message", "")
        if exc.code == 404 and "certificate has not finished" in detail.lower():
            print("::warning::GitHub is still issuing the domain certificate. HTTPS enforcement will retry on the next site deployment.")
            return False
        if exc.code == 403:
            print("::warning::The certificate is ready, but this workflow cannot change HTTPS enforcement. The repository owner must enable Enforce HTTPS at https://github.com/AIConvoCast/AIConvoCast/settings/pages")
            return False
        raise
    print("HTTPS enforcement enabled.")
    return True


def check_site():
    now = datetime.now(timezone.utc)
    for host in ("aiconvocast.com", "www.aiconvocast.com"):
        with socket.create_connection((host, 443), timeout=20) as sock:
            with ssl.create_default_context().wrap_socket(sock, server_hostname=host) as connection:
                expires = ssl.cert_time_to_seconds(connection.getpeercert()["notAfter"])
                days = (expires - now.timestamp()) / 86400
                if days < 14:
                    raise RuntimeError(f"{host}: certificate expires in {days:.1f} days")
                print(f"{host}: trusted certificate, {days:.0f} days remaining")
        for scheme in ("http", "https"):
            with urlopen(f"{scheme}://{host}/", timeout=20) as response:
                url = urlsplit(response.url)
                if url.scheme != "https" or url.hostname != "aiconvocast.com":
                    raise RuntimeError(f"{scheme}://{host}/ did not redirect to the canonical HTTPS site")
    with urlopen("https://aiconvocast.com/site-status.json", timeout=20) as response:
        status = json.load(response)
    built = datetime.fromisoformat(status["built_at"])
    if (now - built).total_seconds() > 86400 or status["episode_count"] < 1:
        raise RuntimeError("Scheduled site refresh is stale or the episode archive is empty")
    print(f"Site refreshed at {built.isoformat()}; {status['episode_count']} episodes")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--enable-https", action="store_true")
    args = parser.parse_args()
    enable_https_when_ready() if args.enable_https else check_site()
