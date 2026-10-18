let apiPromise;
function loadPlayerAPI() {
  if (window.YT?.Player) return Promise.resolve(window.YT);
  if (apiPromise) return apiPromise;
  apiPromise = new Promise((resolve, reject) => {
    const script = document.createElement("script");
    const timeout = setTimeout(
      () => reject(new Error("Player unavailable")),
      15000,
    );
    window.onYouTubeIframeAPIReady = () => {
      clearTimeout(timeout);
      resolve(window.YT);
    };
    script.src = "https://www.youtube.com/iframe_api";
    script.onerror = () => {
      clearTimeout(timeout);
      reject(new Error("Player unavailable"));
    };
    document.head.append(script);
  }).catch((error) => {
    apiPromise = undefined;
    throw error;
  });
  return apiPromise;
}

export function captionAt(cues, time) {
  return cues.find((cue) => time >= cue.start && time < cue.end)?.text || "";
}

export function validCaptions(cues) {
  return (
    Array.isArray(cues) &&
    cues.length > 0 &&
    cues.length < 1000 &&
    cues.every(
      (cue, index) =>
        cue &&
        Number.isFinite(cue.start) &&
        Number.isFinite(cue.end) &&
        cue.start >= 0 &&
        cue.end > cue.start &&
        typeof cue.text === "string" &&
        cue.text.length < 1000 &&
        (!index || cue.start >= cues[index - 1].end),
    )
  );
}

export function setupVideo() {
  const trigger = document.querySelector("[data-video-play]");
  const dialog = document.getElementById("video-dialog");
  if (!trigger || !dialog) return;
  const stage = dialog.querySelector(".video-stage");
  const caption = dialog.querySelector(".video-caption");
  const close = dialog.querySelector("[data-video-close]");
  const fullscreen = dialog.querySelector("[data-video-fullscreen]");
  let player,
    timer,
    request,
    generation = 0;

  function cleanup() {
    generation++;
    request?.abort();
    clearInterval(timer);
    player?.destroy();
    player = undefined;
    stage.replaceChildren();
    document.documentElement.classList.remove("video-open");
    if (document.fullscreenElement === dialog)
      document.exitFullscreen().catch(() => {});
  }
  function dismiss() {
    if (!dialog.open) return;
    dialog.close();
    cleanup();
    trigger.focus({ preventScroll: true });
  }
  function closeVideo() {
    dismiss();
    if (history.state?.communityVideo) history.back();
  }
  window.addEventListener("popstate", dismiss);
  close.addEventListener("click", closeVideo);
  dialog.addEventListener("cancel", (event) => {
    event.preventDefault();
    closeVideo();
  });
  dialog.addEventListener("click", (event) => {
    if (event.target !== dialog) return;
    const rect = dialog.getBoundingClientRect();
    if (
      event.clientX < rect.left ||
      event.clientX > rect.right ||
      event.clientY < rect.top ||
      event.clientY > rect.bottom
    )
      closeVideo();
  });
  fullscreen.hidden = !dialog.requestFullscreen;
  fullscreen.addEventListener("click", () => {
    const action = document.fullscreenElement
      ? document.exitFullscreen()
      : dialog.requestFullscreen();
    action.catch(() => {});
  });
  window.addEventListener("pagehide", () => {
    dismiss();
  });

  trigger.addEventListener("click", async () => {
    if (dialog.open) return;
    const current = ++generation;
    const url = new URL(location.href);
    url.hash = "video";
    history.pushState({ ...history.state, communityVideo: true }, "", url);
    dialog.showModal();
    document.documentElement.classList.add("video-open");
    close.focus();
    caption.textContent = dialog.dataset.loading;
    const mount = document.createElement("div");
    stage.replaceChildren(mount);
    request = new AbortController();
    const subtitles = fetch(trigger.dataset.captions, {
      signal: request.signal,
    })
      .then((response) => {
        if (!response.ok) throw new Error("Captions unavailable");
        return response.json();
      })
      .then((cues) => {
        if (!validCaptions(cues)) throw new Error("Invalid captions");
        return cues;
      })
      .catch(() => null);
    try {
      const api = await loadPlayerAPI();
      if (current !== generation) return;
      const cues = await subtitles;
      if (current !== generation) return;
      caption.textContent = cues ? dialog.dataset.ready : dialog.dataset.error;
      const sync = () => {
        if (current !== generation || !player || !cues) return;
        const state = player.getPlayerState();
        const text = [1, 2, 3].includes(state)
          ? captionAt(cues, player.getCurrentTime())
          : "";
        caption.textContent =
          text || ([0, 1, 2, 3].includes(state) ? "" : dialog.dataset.ready);
      };
      player = new api.Player(mount, {
        host: "https://www.youtube-nocookie.com",
        width: "100%",
        height: "100%",
        videoId: "Ze1cUR-MSyg",
        playerVars: {
          hl: document.documentElement.lang,
          playsinline: 1,
          autoplay: 0,
          origin: location.origin,
        },
        events: {
          onReady: () => {
            if (current === generation) timer = setInterval(sync, 100);
          },
          onStateChange: sync,
          onError: () => {
            if (current !== generation) return;
            clearInterval(timer);
            caption.textContent = dialog.dataset.error;
          },
        },
      });
    } catch {
      if (current === generation) caption.textContent = dialog.dataset.error;
    }
  });
}
