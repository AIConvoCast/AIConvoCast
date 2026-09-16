# AI Convo Cast website

GitHub Pages serves the generated `public/` artifact. In repository **Settings >
Pages**, the source must be **GitHub Actions**, with custom domain `aiconvocast.com`
and **Enforce HTTPS** enabled after GitHub issues its domain certificate.

The deploy workflow builds from the Spotify/Anchor RSS feed every two hours and
when website files change. It creates permanent episode URLs, full show notes,
paginated archives, canonical links, podcast structured data, a sitemap, and
robots.txt. Feed failures stop deployment and retain the previous site.
GitHub may delay scheduled jobs. `site-status.json` records build freshness;
the daily website check fails if the build is older than 24 hours, either domain
has invalid TLS, HTTPS redirects are missing, or certificate expiry is near.

For a local preview, use a new empty output directory:

```powershell
python -m unittest test_site -v
python build_site.py --output public
python -m http.server 8765 --bind 127.0.0.1 --directory public
```

Do not publish the source directory: its HTML files contain build placeholders.
The builder copies only explicitly listed public assets. Feed text is escaped;
scripts from show notes cannot run. The site uses local fonts, no analytics,
HTTPS media, and a restrictive content policy. GitHub Pages manages TLS and
HTTP headers; page markup cannot repair a missing domain certificate.

Run `python check_site.py` after deployment. Submit
`https://aiconvocast.com/sitemap.xml` in the site's verified Google Search Console
property. The sitemap aids discovery; indexing and search ranking are controlled
by search engines.

If TLS is stuck, check both apex and www DNS using GitHub's Pages health check.
Follow [GitHub's HTTPS troubleshooting](https://docs.github.com/en/pages/getting-started-with-github-pages/securing-your-github-pages-site-with-https).
Do not bypass certificate validation or substitute an HTTP canonical URL.
