import assert from "node:assert/strict";
import { readFileSync, readdirSync } from "node:fs";
import { test } from "node:test";
import { JSDOM } from "jsdom";
import { captionAt, validCaptions, setupVideo } from "../site/video.js";

test("caption timing follows seeking, pause and exact boundaries in all ten languages", () => {
  const files = readdirSync(new URL("../site/captions/", import.meta.url));
  assert.equal(files.length, 10);
  for (const file of files) {
    const cues = JSON.parse(
      readFileSync(
        new URL(`../site/captions/${file}`, import.meta.url),
        "utf8",
      ),
    );
    assert.ok(validCaptions(cues), file);
    assert.equal(captionAt(cues, 0), "");
    assert.equal(captionAt(cues, 12), cues[2].text);
    assert.equal(captionAt(cues, 4.32), cues[1].text);
    assert.equal(captionAt(cues, 2), cues[0].text);
    assert.equal(captionAt(cues, 146.52), "");
  }
  for (const invalid of [
    null,
    [],
    [null],
    [{ start: 1, end: 0, text: "bad" }],
  ]) {
    assert.equal(validCaptions(invalid), false);
  }
});

test("lightbox is lazy, tracks the player clock and destroys playback on close", async () => {
  const dom = new JSDOM(
    `<button data-video-play data-captions="/captions/es.json">Video</button>
    <dialog id="video-dialog" data-loading="Loading" data-ready="Ready" data-error="Error">
    <button data-video-close>Close</button><button data-video-fullscreen>Expand</button>
    <div class="video-stage"></div><p class="video-caption"></p></dialog>`,
    { url: "https://example.com/es/" },
  );
  const { window } = dom;
  const dialog = window.document.querySelector("dialog")!;
  dialog.showModal = () => dialog.setAttribute("open", "");
  dialog.close = () => dialog.removeAttribute("open");
  let clock = 1,
    state = 1,
    destroyed = 0,
    calls = 0;
  let events: Record<string, () => void>;
  let tick: () => void;
  const globals = {
    window,
    document: window.document,
    history: window.history,
    location: window.location,
    fetch: async () => {
      calls++;
      return {
        ok: true,
        json: async () => [
          { start: 0, end: 3, text: "Hola" },
          { start: 3, end: 6, text: "Mundo" },
        ],
      };
    },
    setInterval: (callback: () => void) => {
      tick = callback;
      return 1;
    },
    clearInterval: () => {},
  };
  const originals = new Map(
    Object.keys(globals).map((key) => [
      key,
      Object.getOwnPropertyDescriptor(globalThis, key),
    ]),
  );
  for (const [key, value] of Object.entries(globals))
    Object.defineProperty(globalThis, key, {
      configurable: true,
      writable: true,
      value,
    });
  Object.assign(window, {
    YT: {
      Player: class {
        constructor(
          _mount: unknown,
          options: { events: Record<string, () => void> },
        ) {
          events = options.events;
        }
        getCurrentTime() {
          return clock;
        }
        getPlayerState() {
          return state;
        }
        destroy() {
          destroyed++;
        }
      },
    },
  });
  try {
    setupVideo();
    assert.equal(calls, 0);
    assert.equal(window.document.querySelectorAll("iframe, script").length, 0);
    const trigger =
      window.document.querySelector<HTMLButtonElement>("[data-video-play]")!;
    trigger.click();
    await new Promise((resolve) => setTimeout(resolve, 0));
    assert.equal(calls, 1);
    assert.equal(dialog.open, true);
    assert.equal(window.document.activeElement?.textContent, "Close");
    events!.onReady();
    tick!();
    assert.equal(window.document.querySelector("p")!.textContent, "Hola");
    clock = 4;
    state = 2;
    tick!();
    assert.equal(window.document.querySelector("p")!.textContent, "Mundo");
    clock = 1;
    tick!();
    assert.equal(window.document.querySelector("p")!.textContent, "Hola");
    dialog.dispatchEvent(new window.Event("cancel", { cancelable: true }));
    assert.equal(dialog.open, false);
    assert.equal(destroyed, 1);
    assert.equal(window.document.activeElement, trigger);
    assert.equal(
      window.document.documentElement.classList.contains("video-open"),
      false,
    );
  } finally {
    dom.window.close();
    for (const [key, descriptor] of originals) {
      if (descriptor) Object.defineProperty(globalThis, key, descriptor);
      else Reflect.deleteProperty(globalThis, key);
    }
  }
});
