// Episode content is built into the HTML, even when JavaScript is disabled.
const year = document.getElementById("year");
if (year) year.textContent = String(new Date().getFullYear());

// Avoid competing players when a visitor switches episodes.
document.addEventListener("play", (event) => {
  if (!(event.target instanceof HTMLAudioElement)) return;
  document.querySelectorAll("audio").forEach((player) => {
    if (player !== event.target) player.pause();
  });
}, true);
