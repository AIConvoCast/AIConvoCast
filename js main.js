// main.js - AI Convo Cast
const RSS_FEED_URL = "https://anchor.fm/s/101530384/podcast/rss";
const CACHE_KEY = "aiconvocast_rss_cache";
const CACHE_TIME = 2 * 60 * 60 * 1000; // 2 hours

function sanitizeHTML(str) {
  const temp = document.createElement('div');
  temp.textContent = str;
  return temp.innerHTML;
}

function formatDate(dateStr) {
  const d = new Date(dateStr);
  return d.toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' });
}

function excerpt(str, len = 30) {
  return str.length > len ? str.slice(0, len) + "…" : str;
}

function getImageFromItem(item) {
  // Try to get image from <itunes:image> or <image> or fallback
  const itunesImg = item.querySelector("itunes\\:image, image");
  return itunesImg ? itunesImg.getAttribute("href") || itunesImg.textContent : "https://static-1.anchor.com/podcast_image_placeholder.png";
}

async function fetchFeed() {
  // Check cache
  const cache = localStorage.getItem(CACHE_KEY);
  if (cache) {
    const { time, data } = JSON.parse(cache);
    if (Date.now() - time < CACHE_TIME) {
      return new window.DOMParser().parseFromString(data, "text/xml");
    }
  }
  // Fetch RSS
  const resp = await fetch(RSS_FEED_URL);
  if (!resp.ok) throw new Error("Failed to fetch RSS feed");
  const text = await resp.text();
  localStorage.setItem(CACHE_KEY, JSON.stringify({ time: Date.now(), data: text }));
  return new window.DOMParser().parseFromString(text, "text/xml");
}

function renderEpisodes(doc) {
  const items = Array.from(doc.querySelectorAll("item"));
  const grid = document.getElementById("episodes-grid");
  grid.innerHTML = "";
  items.forEach(item => {
    const title = sanitizeHTML(item.querySelector("title")?.textContent || "Untitled");
    const pubDate = formatDate(item.querySelector("pubDate")?.textContent || "");
    const descRaw = item.querySelector("description")?.textContent || "";
    const desc = sanitizeHTML(descRaw.replace(/<[^>]+>/g, ''));
    const excerptText = excerpt(desc, 100);
    const audioUrl = item.querySelector("enclosure")?.getAttribute("url") || "";
    const imgUrl = getImageFromItem(item);

    const card = document.createElement("article");
    card.className = "episode-card";
    card.innerHTML = `
      <img src="${imgUrl}" alt="Episode cover" class="episode-thumb" width="300" height="300" loading="lazy">
      <div class="episode-title">${title}</div>
      <div class="episode-date">${pubDate}</div>
      <div class="episode-desc">${excerptText}</div>
      <audio class="episode-audio" controls preload="none" aria-label="Audio player for ${title}">
        <source src="${audioUrl}" type="audio/mpeg">
        Your browser does not support the audio element.
      </audio>
    `;
    grid.appendChild(card);
  });
}

async function loadEpisodes() {
  const errorDiv = document.getElementById("episodes-error");
  try {
    const doc = await fetchFeed();
    renderEpisodes(doc);
    errorDiv.style.display = "none";
  } catch (e) {
    errorDiv.textContent = "Sorry, we couldn't load episodes right now. Please try again later.";
    errorDiv.style.display = "block";
  }
}

window.addEventListener("DOMContentLoaded", loadEpisodes);
