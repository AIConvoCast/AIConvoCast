// main.js - AI Convo Cast
const RSS_FEED_URL = "https://anchor.fm/s/101530384/podcast/rss";
const CACHE_KEY = "aiconvocast_rss_cache_v2";
const FALLBACK_IMAGE = "ai-convo-cast-logo.jpg";

function textFromHTML(value) {
  const temp = document.createElement("div");
  temp.innerHTML = value == null ? "" : String(value);
  return (temp.textContent || "").replace(/\s+/g, " ").trim();
}

function excerpt(value, length = 140) {
  const text = textFromHTML(value);
  return text.length > length ? `${text.slice(0, length).trim()}...` : text;
}

function formatDate(dateValue) {
  const date = new Date(dateValue);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleDateString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}

function safeUrl(value, fallback = "") {
  if (!value) return fallback;
  try {
    const url = new URL(value, window.location.href);
    return url.protocol === "https:" || url.origin === window.location.origin ? url.href : fallback;
  } catch {
    return fallback;
  }
}

function child(parent, tag, className, text) {
  const element = document.createElement(tag);
  if (className) element.className = className;
  if (text) element.textContent = text;
  parent.appendChild(element);
  return element;
}

function getFirst(item, selectors) {
  for (const selector of selectors) {
    const found = item.querySelector(selector);
    if (found) return found;
  }
  return null;
}

function parseEpisode(item) {
  const title = textFromHTML(getFirst(item, ["title"])?.textContent || "Untitled episode");
  const description = getFirst(item, ["description", "content\\:encoded"])?.textContent || "";
  const pubDateRaw = getFirst(item, ["pubDate"])?.textContent || "";
  const image = getFirst(item, ["itunes\\:image", "image"])?.getAttribute("href")
    || getFirst(item, ["image"])?.textContent
    || FALLBACK_IMAGE;

  return {
    title,
    description,
    pubDateRaw,
    pubTime: new Date(pubDateRaw).getTime() || 0,
    link: safeUrl(getFirst(item, ["link"])?.textContent || ""),
    image: safeUrl(image, FALLBACK_IMAGE),
    audio: safeUrl(getFirst(item, ["enclosure"])?.getAttribute("url") || ""),
  };
}

async function fetchFeed() {
  let cachedText = "";
  try {
    cachedText = JSON.parse(localStorage.getItem(CACHE_KEY) || "null")?.data || "";
  } catch {
    localStorage.removeItem(CACHE_KEY);
  }

  try {
    const response = await fetch(RSS_FEED_URL, { cache: "reload" });
    if (!response.ok) throw new Error(`RSS feed returned ${response.status}`);
    const text = await response.text();
    localStorage.setItem(CACHE_KEY, JSON.stringify({ time: Date.now(), data: text }));
    return new DOMParser().parseFromString(text, "text/xml");
  } catch (error) {
    if (!cachedText) throw error;
    return new DOMParser().parseFromString(cachedText, "text/xml");
  }
}

function buildEpisodeCard(episode, options = {}) {
  const card = document.createElement("article");
  card.className = options.featured ? "episode-card latest-episode" : "episode-card";
  card.setAttribute("aria-label", `${options.featured ? "Latest episode" : "Episode"}: ${episode.title}`);

  const image = child(card, "img", "episode-thumb");
  image.src = episode.image;
  image.alt = `Cover art for ${episode.title}`;
  image.width = 300;
  image.height = 300;
  image.loading = options.featured ? "eager" : "lazy";
  image.decoding = "async";
  image.addEventListener("error", () => {
    image.src = FALLBACK_IMAGE;
  }, { once: true });

  if (options.featured) child(card, "div", "episode-kicker", "Newest episode");
  child(card, "h3", "episode-title", episode.title);
  child(card, "div", "episode-date", formatDate(episode.pubDateRaw));
  child(card, "p", "episode-desc", excerpt(episode.description, options.featured ? 220 : 130));

  if (episode.audio) {
    const audio = child(card, "audio", "episode-audio");
    audio.controls = true;
    audio.preload = "none";
    audio.setAttribute("aria-label", `Audio player for ${episode.title}`);
    const source = child(audio, "source");
    source.src = episode.audio;
    source.type = "audio/mpeg";
  }

  if (episode.link) {
    const link = child(card, "a", "episode-link", "Open episode page");
    link.href = episode.link;
    link.target = "_blank";
    link.rel = "noopener noreferrer";
  }

  return card;
}

function updateSocialImage(episode) {
  const ogImage = document.querySelector('meta[property="og:image"]');
  const twitterImage = document.querySelector('meta[name="twitter:image"]');
  if (ogImage) ogImage.content = episode.image;
  if (twitterImage) twitterImage.content = episode.image;
}

function renderEpisodes(doc) {
  const grid = document.getElementById("episodes-grid");
  if (!grid) return;

  const highlight = document.getElementById("latest-episode-highlight");
  const status = document.getElementById("episodes-error");
  const episodes = Array.from(doc.querySelectorAll("item"))
    .map(parseEpisode)
    .sort((a, b) => b.pubTime - a.pubTime);

  grid.replaceChildren();
  if (highlight) highlight.replaceChildren();

  if (!episodes.length) {
    if (status) {
      status.textContent = "No episodes were found in the podcast feed.";
      status.style.display = "block";
    }
    return;
  }

  updateSocialImage(episodes[0]);

  if (highlight) {
    highlight.appendChild(buildEpisodeCard(episodes[0], { featured: true }));
  }

  const limitValue = grid.dataset.limit || "all";
  const limit = limitValue === "all" ? episodes.length : Number.parseInt(limitValue, 10);
  const offset = highlight ? 1 : 0;
  const visibleEpisodes = episodes.slice(offset, offset + (Number.isFinite(limit) ? limit : episodes.length));

  visibleEpisodes.forEach((episode) => {
    grid.appendChild(buildEpisodeCard(episode));
  });

  if (status) status.style.display = "none";
}

async function loadEpisodes() {
  const status = document.getElementById("episodes-error");
  if (status) {
    status.textContent = "Loading the latest episodes...";
    status.style.display = "block";
  }

  try {
    renderEpisodes(await fetchFeed());
  } catch (error) {
    console.error(error);
    if (status) {
      status.textContent = "Sorry, we couldn't load episodes right now. You can still use the RSS feed link below.";
      status.style.display = "block";
    }
  }
}

document.addEventListener("DOMContentLoaded", loadEpisodes);
