"""Offline checks for safe, crawlable site generation; never publish or submit forms."""

from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import tempfile
import unittest
import xml.etree.ElementTree as ET

import build_site as site


def feed(count=2):
    root = ET.Element("rss")
    channel = ET.SubElement(root, "channel")
    for index in range(count):
        item = ET.SubElement(channel, "item")
        for key, value in {
            "title": f"AI news {index}", "guid": f"stable-{index}",
            "description": "<p>Useful AI news &amp; analysis.</p><p>More context.</p>",
            "pubDate": format_datetime(datetime(2026, 9, 1, tzinfo=timezone.utc) + timedelta(days=index)),
            "link": f"https://podcasters.spotify.com/episode/{index}",
            f"{site.ITUNES}duration": "07:30",
        }.items():
            ET.SubElement(item, key).text = value
        ET.SubElement(item, "enclosure", url="https://anchor.fm/audio.mp3", type="audio/mpeg")
    return ET.tostring(root)


class HTMLCheck(HTMLParser):
    def __init__(self, text):
        super().__init__()
        self.tags = []
        self.feed(text)

    def handle_starttag(self, tag, attrs):
        self.tags.append((tag, dict(attrs)))


class SiteTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.output = Path(self.temp.name) / "site"

    def test_newest_first_and_stable_urls_after_title_corrections(self):
        original = site.parse_feed(feed())
        corrected = site.parse_feed(feed().replace(b"AI news 1", b"Corrected title"))
        self.assertEqual(original[0]["title"], "AI news 1")
        self.assertEqual(original[0]["path"], corrected[0]["path"])
        self.assertEqual(original[0]["duration"], "PT450S")

    def test_invalid_feed_never_replaces_existing_deployment(self):
        self.output.mkdir()
        previous = self.output / "index.html"
        previous.write_text("Previous deployment")
        for content in [b"<html>error</html>", b"<rss><channel/></rss>", b"not xml", b'<!DOCTYPE rss [<!ENTITY x "bad">]><rss><channel/></rss>']:
            with self.subTest(content=content):
                with self.assertRaises((ValueError, ET.ParseError)):
                    site.build_site(content, self.output)
                self.assertEqual(previous.read_text(), "Previous deployment")

    def test_unexpected_files_cannot_enter_public_artifact(self):
        result = site.build_site(feed(), self.output)
        self.assertEqual(result["episodes"], 2)
        for path in self.output.rglob("*"):
            if path.is_file():
                self.assertIn(path.suffix, {".html", ".css", ".js", ".jpg", ".json", ".xml", ".txt", ""})
                self.assertNotIn(path.name, {"jmio-google-api.json", "ai_podcast_pipeline_for_cursor.py", "requirements.txt"})
        with self.assertRaises(ValueError):
            site.build_site(feed(), self.output)
        with self.assertRaises(ValueError):
            site.build_site(feed(), site.ROOT)

    def test_archive_pagination_and_sitemap_link_every_episode(self):
        site.build_site(feed(25), self.output)
        episodes = site.parse_feed(feed(25))
        archive = (self.output / "episodes.html").read_text(encoding="utf-8")
        older = (self.output / "episodes/page/2/index.html").read_text(encoding="utf-8")
        self.assertEqual(archive.count('class="episode-card"'), 24)
        self.assertEqual(older.count('class="episode-card"'), 1)
        self.assertIn('rel="next" href="/episodes/page/2/"', archive)
        self.assertIn('rel="prev" href="/episodes.html"', older)
        ns = {"s": "http://www.sitemaps.org/schemas/sitemap/0.9"}
        sitemap = ET.parse(self.output / "sitemap.xml")
        urls = {element.text for element in sitemap.findall("s:url/s:loc", ns)}
        for episode in episodes:
            self.assertIn(site.SITE_URL + episode["path"], urls)
            self.assertTrue((self.output / episode["path"].lstrip("/") / "index.html").is_file())
        self.assertIn("Sitemap: https://aiconvocast.com/sitemap.xml", (self.output / "robots.txt").read_text())

    def test_episode_html_has_notes_and_matching_metadata_without_javascript(self):
        site.build_site(feed(), self.output)
        episode = site.parse_feed(feed())[0]
        document = (self.output / episode["path"].lstrip("/") / "index.html").read_text(encoding="utf-8")
        self.assertIn("<h1>AI news 1</h1>", document)
        self.assertIn("Useful AI news &amp; analysis.", document)
        self.assertIn('preload="none"', document)
        schema = json.loads(re.search(r'<script type="application/ld\+json">(.*?)</script>', document, re.S).group(1))
        self.assertEqual(schema["@type"], "PodcastEpisode")
        self.assertEqual(schema["datePublished"], episode["date"])
        self.assertEqual(schema["url"], site.SITE_URL + episode["path"])
        self.assertNotIn("{{", document)

    def test_rss_markup_and_unsafe_urls_cannot_execute(self):
        root = ET.fromstring(feed(1))
        item = root.find("./channel/item")
        item.find("title").text = '<img src=x onerror="alert(1)">Title & company'
        item.find("description").text = '<p>Safe notes</p><script>alert(1)</script><img src=x onerror="alert(2)"><p>More notes</p>'
        item.find("link").text = "javascript:alert(1)"
        item.find("enclosure").set("url", "http://insecure.example/audio.mp3")
        content = ET.tostring(root)
        site.build_site(content, self.output)
        for path in self.output.rglob("*.html"):
            text = path.read_text(encoding="utf-8")
            self.assertNotIn("onerror=", text)
            self.assertNotIn("alert(", text)
            self.assertNotIn("javascript:", text)
            self.assertNotIn("insecure.example", text)

    def test_json_metadata_cannot_close_its_script_element(self):
        result = site.metadata("<head></head>", "Test", 'Quote " & more', "/", {"description": "</script><script>injected</script>"})
        self.assertEqual(result.count("</script>"), 1)
        self.assertIn("\\u003c/script\\u003e", result)

    def test_all_pages_have_secure_assets_and_one_canonical(self):
        site.build_site(feed(), self.output)
        for path in self.output.rglob("*.html"):
            tags = HTMLCheck(path.read_text(encoding="utf-8")).tags
            canonicals = [attrs["href"] for tag, attrs in tags if tag == "link" and attrs.get("rel") == "canonical"]
            self.assertEqual(len(canonicals), 1)
            self.assertTrue(canonicals[0].startswith(site.SITE_URL))
            for tag, attrs in tags:
                if tag == "script" and attrs.get("type") != "application/ld+json":
                    self.assertTrue(attrs.get("src", "").startswith("/"))
                for name in ["href", "src", "action"]:
                    self.assertFalse(attrs.get(name, "").startswith("http:"))
            csp = next(attrs["content"] for tag, attrs in tags if attrs.get("http-equiv") == "Content-Security-Policy")
            self.assertNotIn("unsafe-inline", csp)
            self.assertIn("object-src 'none'", csp)

    def test_status_timestamp_and_404(self):
        now = datetime(2026, 9, 16, 12, tzinfo=timezone.utc)
        site.build_site(feed(), self.output, now=now)
        status = json.loads((self.output / "site-status.json").read_text())
        self.assertEqual(status["built_at"], now.isoformat())
        self.assertEqual(status["episode_count"], 2)
        self.assertIn('content="noindex,follow"', (self.output / "404.html").read_text())


if __name__ == "__main__":
    unittest.main()
