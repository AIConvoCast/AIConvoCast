"""Build crawlable podcast pages from RSS; only public assets enter the output.

Feed failures stop deployment, leaving the previously published site available.
"""

import argparse
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import hashlib
import html
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import shutil
from urllib.parse import urlsplit
from urllib.request import Request, urlopen
import xml.etree.ElementTree as ET

SITE_URL = "https://aiconvocast.com"
FEED_URL = "https://anchor.fm/s/101530384/podcast/rss"
ROOT = Path(__file__).resolve().parent
PAGE_SIZE = 24
MAX_FEED_BYTES = 8 * 1024 * 1024
PUBLIC_ASSETS = ("styles.css", "main.js", "contact.js", "ai-convo-cast-logo.jpg", "manifest.json", "CNAME")
ITUNES = "{http://www.itunes.com/dtds/podcast-1.0.dtd}"


class DescriptionText(HTMLParser):
    """Extract text without inserting executable feed markup into the site."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.hidden = 0

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style", "iframe", "object", "svg"}:
            self.hidden += 1
        if not self.hidden and tag in {"p", "div", "br", "li", "h2", "h3"}:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in {"script", "style", "iframe", "object", "svg"} and self.hidden:
            self.hidden -= 1
        if not self.hidden and tag in {"p", "div", "li", "h2", "h3"}:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(data)


def plain_text(value):
    parser = DescriptionText()
    parser.feed(value or "")
    return "\n\n".join(filter(None, (" ".join(line.split()) for line in "".join(parser.parts).splitlines())))


def https_url(value):
    value = (value or "").strip()
    try:
        url = urlsplit(value)
        if url.scheme == "https" and url.hostname and not url.username and not url.password:
            return value
    except ValueError:
        pass
    return ""


def duration_iso(value):
    try:
        parts = [int(part) for part in value.split(":")]
        if not 1 <= len(parts) <= 3 or any(part < 0 for part in parts):
            return None
        seconds = sum(part * 60 ** index for index, part in enumerate(reversed(parts)))
        return f"PT{seconds}S" if seconds else None
    except (ValueError, AttributeError):
        return None


def parse_feed(content):
    if len(content) > MAX_FEED_BYTES or b"<!DOCTYPE" in content.upper() or b"<!ENTITY" in content.upper():
        raise ValueError("RSS is oversized or contains an unsupported XML declaration")
    root = ET.fromstring(content)
    if root.tag != "rss" or root.find("channel") is None:
        raise ValueError("Expected a podcast RSS channel")
    episodes, seen = [], set()
    for item in root.findall("./channel/item"):
        title = plain_text(item.findtext("title"))
        link = https_url(item.findtext("link"))
        identity = (item.findtext("guid") or link).strip()
        if not title or not identity:
            raise ValueError("Episode is missing a title or stable identifier")
        if identity in seen:
            continue
        seen.add(identity)
        try:
            date = parsedate_to_datetime(item.findtext("pubDate") or "")
            if date.tzinfo is None:
                date = date.replace(tzinfo=timezone.utc)
            date = date.astimezone(timezone.utc)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Invalid publication date for {title}") from exc
        enclosure = item.find("enclosure")
        audio = https_url(enclosure.get("url")) if enclosure is not None else ""
        # Stable GUID-based URLs survive corrections to an episode's title.
        slug = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:20]
        episodes.append({
            "title": title, "description": plain_text(item.findtext("description")),
            "date": date.isoformat().replace("+00:00", "Z"),
            "display_date": f"{date:%b} {date.day}, {date.year}",
            "path": f"/episodes/{slug}/", "audio": audio, "link": link,
            "duration": duration_iso(item.findtext(f"{ITUNES}duration")),
        })
    if not episodes:
        raise ValueError("RSS has no episodes; refusing to replace the live archive")
    return sorted(episodes, key=lambda item: item["date"], reverse=True)


def summary(episode, limit=160):
    text = episode["description"].split("\n\n")[0]
    return text if len(text) <= limit else text[:limit - 1].rsplit(" ", 1)[0] + "…"


def audio_player(episode):
    if not episode["audio"]:
        return ""
    return (f'<audio class="episode-audio" controls preload="none" aria-label="Listen to {html.escape(episode["title"], quote=True)}">'
            f'<source src="{html.escape(episode["audio"], quote=True)}" type="audio/mpeg">'
            'Your browser does not support this audio player.</audio>')


def episode_card(episode, featured=False):
    title = html.escape(episode["title"])
    image = ('<img class="episode-thumb" src="/ai-convo-cast-logo.jpg" alt="AI Convo Cast cover art" '
             'width="300" height="300" decoding="async" loading="' + ("eager" if featured else "lazy") + '">')
    return (
        f'<article class="episode-card{" latest-episode" if featured else ""}">{image}'
        + ('<div class="episode-kicker">Newest episode</div>' if featured else "")
        + f'<h3 class="episode-title"><a href="{episode["path"]}">{title}</a></h3>'
        f'<time class="episode-date" datetime="{episode["date"]}">{episode["display_date"]}</time>'
        f'<p class="episode-desc">{html.escape(summary(episode, 260 if featured else 160))}</p>'
        + (audio_player(episode) if featured else "")
        + f'<a class="episode-link" href="{episode["path"]}">Listen and read show notes</a></article>'
    )


def series_schema():
    return {
        "@context": "https://schema.org", "@type": "PodcastSeries", "@id": SITE_URL + "/#podcast",
        "name": "AI Convo Cast", "url": SITE_URL + "/", "webFeed": FEED_URL,
        "description": "Daily coverage of artificial intelligence news, model launches, AI companies, and technology trends.",
        "image": SITE_URL + "/ai-convo-cast-logo.jpg", "inLanguage": "en-US",
        "publisher": {"@type": "Organization", "name": "AI Convo Cast", "url": SITE_URL + "/"},
        "sameAs": ["https://open.spotify.com/show/23r1mVVSwL937ulIMiJqQ3", "https://podcasts.apple.com/us/podcast/ai-convo-cast/id1796856699"],
    }


def episode_schema(episode):
    result = {
        "@context": "https://schema.org", "@type": "PodcastEpisode",
        "@id": SITE_URL + episode["path"] + "#episode", "url": SITE_URL + episode["path"],
        "name": episode["title"], "description": episode["description"],
        "datePublished": episode["date"], "inLanguage": "en-US", "image": SITE_URL + "/ai-convo-cast-logo.jpg",
        "partOfSeries": {"@type": "PodcastSeries", "@id": SITE_URL + "/#podcast", "name": "AI Convo Cast", "url": SITE_URL + "/"},
    }
    if episode["duration"]:
        result["duration"] = episode["duration"]
    if episode["audio"]:
        result["associatedMedia"] = {"@type": "AudioObject", "contentUrl": episode["audio"], "encodingFormat": "audio/mpeg"}
    return result


def metadata(document, title, description, path, schema=None):
    document = re.sub(r'<title>.*?</title>', lambda _: f'<title>{html.escape(title)}</title>', document, flags=re.S)
    document = re.sub(r'<meta (?:name="(?:description|twitter:[^"]+)"|property="og:[^"]+")[^>]*>\s*', '', document)
    document = re.sub(r'<link rel="canonical"[^>]*>\s*', '', document)
    document = re.sub(r'<script type="application/ld\+json">.*?</script>\s*', '', document, flags=re.S)
    entries = {"description": description, "twitter:card": "summary_large_image", "twitter:title": title, "twitter:description": description, "twitter:image": SITE_URL + "/ai-convo-cast-logo.jpg"}
    tags = [f'<meta name="{key}" content="{html.escape(value, quote=True)}">' for key, value in entries.items()]
    for key, value in {"title": title, "description": description, "url": SITE_URL + path, "image": SITE_URL + "/ai-convo-cast-logo.jpg", "type": "website", "site_name": "AI Convo Cast", "locale": "en_US"}.items():
        tags.append(f'<meta property="og:{key}" content="{html.escape(value, quote=True)}">')
    tags.append(f'<link rel="canonical" href="{SITE_URL + path}">')
    if schema:
        encoded = json.dumps(schema, ensure_ascii=False).replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
        tags.append(f'<script type="application/ld+json">{encoded}</script>')
    return document.replace("</head>", "\n".join(tags) + "\n</head>")


def page_path(number):
    return "/episodes.html" if number == 1 else f"/episodes/page/{number}/"


def pagination(number, total):
    links = []
    if number > 1:
        links.append(f'<a class="episode-link" rel="prev" href="{page_path(number - 1)}">Newer episodes</a>')
    links.append(f'<span>Page {number} of {total}</span>')
    if number < total:
        links.append(f'<a class="episode-link" rel="next" href="{page_path(number + 1)}">Older episodes</a>')
    return '<nav class="pagination" aria-label="Episode archive pages">' + "".join(links) + '</nav>'


def write_page(output, path, document):
    target = output / (path.lstrip("/") + ("index.html" if path.endswith("/") else ""))
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(document, encoding="utf-8")


def build_site(content, output, source=ROOT, now=None):
    episodes = parse_feed(content)
    now = now or datetime.now(timezone.utc)
    output, source = Path(output).resolve(), Path(source).resolve()
    if output == source or source.is_relative_to(output):
        raise ValueError("Build output must not be the source directory or its parent")
    if output.exists() and any(output.iterdir()):
        raise ValueError("Build into an empty directory to avoid publishing stale or private files")
    output.mkdir(parents=True, exist_ok=True)
    for filename in PUBLIC_ASSETS:
        shutil.copyfile(source / filename, output / filename)
    (output / ".nojekyll").write_text("", encoding="utf-8")
    latest = episodes[0]
    template = (source / "episodes.html").read_text(encoding="utf-8")
    home = (source / "index.html").read_text(encoding="utf-8")
    home = home.replace("{{LATEST_EPISODE}}", episode_card(latest, featured=True))
    home = home.replace("{{EPISODES}}", "\n".join(episode_card(ep) for ep in episodes[1:7]))
    home = home.replace("{{FEED_UPDATED}}", f'Latest release: <time datetime="{latest["date"]}">{latest["display_date"]}</time>')
    home = metadata(home, "AI Convo Cast – Daily AI News Podcast", "Listen to daily AI news, model launches, and company updates. Latest episode: " + latest["title"], "/", series_schema())
    write_page(output, "/", home)
    sitemap = [("/", latest["date"])]
    total = (len(episodes) + PAGE_SIZE - 1) // PAGE_SIZE
    for number in range(1, total + 1):
        batch = episodes[(number - 1) * PAGE_SIZE:number * PAGE_SIZE]
        archive = template.replace("{{EPISODES}}", "\n".join(map(episode_card, batch)))
        archive = archive.replace("{{PAGINATION}}", pagination(number, total))
        archive = archive.replace("{{FEED_UPDATED}}", f'{len(episodes)} episodes · Latest release: {latest["display_date"]}')
        schema = {"@context": "https://schema.org", "@type": "ItemList", "itemListElement": [{"@type": "ListItem", "position": index + 1 + (number - 1) * PAGE_SIZE, "url": SITE_URL + ep["path"], "name": ep["title"]} for index, ep in enumerate(batch)]}
        title = "AI News Podcast Episodes – AI Convo Cast" + (f" – Page {number}" if number > 1 else "")
        archive = metadata(archive, title, f"Browse AI Convo Cast's AI news podcast archive. Page {number} of {total}: episode audio, publication dates, and show notes.", page_path(number), schema)
        write_page(output, page_path(number), archive)
        sitemap.append((page_path(number), latest["date"]))
    for episode in episodes:
        notes = "".join(f'<p>{html.escape(paragraph)}</p>' for paragraph in episode["description"].split("\n\n") if paragraph)
        platform = (f'<a class="episode-link" href="{html.escape(episode["link"], quote=True)}" rel="noopener noreferrer">Listen on Spotify</a>' if episode["link"] else "")
        main = (f'<main id="main-content"><section class="page-intro episode-intro"><a class="text-link" href="/episodes.html">All episodes</a>'
                f'<h1>{html.escape(episode["title"])}</h1><time datetime="{episode["date"]}">{episode["display_date"]}</time></section>'
                f'<article class="episode-detail"><div class="episode-listen">{audio_player(episode)}{platform}</div>'
                f'<h2>Show notes</h2><div class="show-notes">{notes}</div></article></main>')
        detail = re.sub(r'<main\b.*?</main>', lambda _: main, template, flags=re.S)
        detail = metadata(detail, episode["title"] + " – AI Convo Cast", summary(episode), episode["path"], episode_schema(episode))
        write_page(output, episode["path"], detail)
        # Publication date is not a modification date; don't invent lastmod.
        sitemap.append((episode["path"], None))
    for filename, title, description in [
        ("contact.html", "Contact AI Convo Cast", "Send AI Convo Cast feedback, story ideas, corrections, and partnership inquiries."),
        ("privacy.html", "Privacy – AI Convo Cast", "How the AI Convo Cast website handles podcast playback, contact messages, and website data."),
    ]:
        document = metadata((source / filename).read_text(encoding="utf-8"), title, description, "/" + filename)
        write_page(output, "/" + filename, document)
        sitemap.append(("/" + filename, None))
    not_found = re.sub(r'<main\b.*?</main>', '<main id="main-content"><section class="page-intro"><h1>Page not found</h1><p>Try the <a href="/">home page</a> or browse <a href="/episodes.html">all episodes</a>.</p></section></main>', template, flags=re.S)
    not_found = metadata(not_found, "Page not found – AI Convo Cast", "This page could not be found.", "/404.html")
    write_page(output, "/404.html", not_found.replace('content="index,follow"', 'content="noindex,follow"'))
    ET.register_namespace("", "http://www.sitemaps.org/schemas/sitemap/0.9")
    urlset = ET.Element("{http://www.sitemaps.org/schemas/sitemap/0.9}urlset")
    for path, modified in sitemap:
        element = ET.SubElement(urlset, "url")
        ET.SubElement(element, "loc").text = SITE_URL + path
        if modified:
            ET.SubElement(element, "lastmod").text = modified
    ET.ElementTree(urlset).write(output / "sitemap.xml", encoding="utf-8", xml_declaration=True)
    (output / "robots.txt").write_text(f"User-agent: *\nAllow: /\nSitemap: {SITE_URL}/sitemap.xml\n", encoding="utf-8")
    (output / "site-status.json").write_text(json.dumps({"built_at": now.isoformat(), "latest_episode_at": latest["date"], "episode_count": len(episodes)}), encoding="utf-8")
    for file in output.rglob("*.html"):
        document = file.read_text(encoding="utf-8").replace('{{YEAR}}', str(now.year))
        if "{{" in document:
            raise ValueError(f"Unfilled template in {file.name}")
        file.write_text(document, encoding="utf-8")
    return {"episodes": len(episodes), "pages": len(sitemap), "latest": latest["date"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "public")
    parser.add_argument("--feed-file", type=Path, help="Use a local RSS fixture instead of fetching the feed")
    args = parser.parse_args()
    if args.feed_file:
        content = args.feed_file.read_bytes()
    else:
        request = Request(FEED_URL, headers={"User-Agent": "AIConvoCast-site-builder", "Cache-Control": "no-cache"})
        with urlopen(request, timeout=30) as response:
            if urlsplit(response.url).scheme != "https":
                raise ValueError("RSS redirected away from HTTPS")
            content = response.read(MAX_FEED_BYTES + 1)
    print(json.dumps(build_site(content, args.output)))


if __name__ == "__main__":
    main()
