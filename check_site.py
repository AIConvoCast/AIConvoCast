"""Check live domain certificates, HTTPS redirects, and scheduled site freshness."""

from datetime import datetime, timezone
import json
import socket
import ssl
from urllib.parse import urlsplit
from urllib.request import urlopen


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
    check_site()
