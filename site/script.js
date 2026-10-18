import { setupVideo } from "./video.js?v=lightbox-1";
import { preferredLocale } from "./language.js";

const languageSelect = document.getElementById("language-select");
const options = [...languageSelect.options];
function localeURL(code) {
  const option = options.find((option) => option.value === code);
  const url = new URL(option.dataset.url, location.href);
  url.search = location.search;
  url.hash = location.hash;
  return url;
}
languageSelect.addEventListener("change", () => {
  try {
    localStorage.setItem("ddu-language", languageSelect.value);
  } catch {}
  location.assign(localeURL(languageSelect.value));
});
if (document.documentElement.dataset.defaultEntry === "true") {
  let saved;
  try {
    saved = localStorage.getItem("ddu-language");
  } catch {}
  const preferred = preferredLocale(
    saved,
    [...(navigator.languages || []), navigator.language],
    options.map((option) => option.value),
  );
  if (preferred !== "en") location.replace(localeURL(preferred));
}

/* The URL stays in the HTML so installation also works without JavaScript. */
const installURL = document.getElementById("install-url");
const status = document.querySelector(".copy-status");
const timers = new Map();

document.querySelectorAll("[data-copy]").forEach((button) => {
  const original = button.innerHTML;
  button.addEventListener("click", async () => {
    clearTimeout(timers.get(button));
    try {
      if (!navigator.clipboard?.writeText)
        throw new Error("Clipboard unavailable");
      await navigator.clipboard.writeText(installURL.value);
      button.textContent = document.body.dataset.copyLabel;
      button.dataset.copied = "true";
      status.textContent = document.body.dataset.copySuccess;
    } catch {
      installURL.focus();
      installURL.select();
      status.textContent = document.body.dataset.copyError;
    }
    timers.set(
      button,
      setTimeout(() => {
        button.innerHTML = original;
        delete button.dataset.copied;
      }, 2400),
    );
  });
});
window.addEventListener("pagehide", () => {
  timers.forEach((timer) => clearTimeout(timer));
});

// YouTube may return a tiny placeholder with HTTP 200 for missing HD thumbnails.
const videoThumbnail = document.querySelector("[data-video-thumbnail]");
if (videoThumbnail) {
  const fallback = () => {
    if (videoThumbnail.src.endsWith("/hqdefault.jpg")) return;
    videoThumbnail.src = "https://i.ytimg.com/vi/Ze1cUR-MSyg/hqdefault.jpg";
  };
  videoThumbnail.addEventListener("error", fallback);
  videoThumbnail.addEventListener("load", () => {
    if (videoThumbnail.naturalWidth < 320) fallback();
  });
  if (videoThumbnail.complete && videoThumbnail.naturalWidth < 320) fallback();
}

setupVideo();
