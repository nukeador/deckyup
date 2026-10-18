import assert from "node:assert/strict";
import { test } from "node:test";
import { registerHooks } from "node:module";
import { JSDOM } from "jsdom";
import { createElement, act } from "react";
import { createRoot } from "react-dom/client";
registerHooks({
  resolve(specifier, context, next) {
    if (specifier === "@decky/api")
      return {
        url: new URL("./mocks/release-api.mjs", import.meta.url).href,
        shortCircuit: true,
      };
    if (specifier === "@decky/ui")
      return {
        url: new URL("./mocks/decky-ui.mjs", import.meta.url).href,
        shortCircuit: true,
      };
    return next(specifier, context);
  },
});
const { ReleaseReview, notesPreview } = await import("../src/ReleaseReview");
const { ReleaseSelector } = await import("../src/ReleaseSelector");
const { PluginDetails } = await import("../src/PluginDetails");

function setup() {
  const dom = new JSDOM('<div id="root"></div>', {
    pretendToBeVisual: true,
    url: "https://test.invalid",
  });
  Object.assign(globalThis, {
    window: dom.window,
    document: dom.window.document,
    HTMLElement: dom.window.HTMLElement,
    requestAnimationFrame: dom.window.requestAnimationFrame.bind(dom.window),
    IS_REACT_ACT_ENVIRONMENT: true,
  });
  const host = document.getElementById("root")!;
  const root = createRoot(host);
  const button = (text: string) =>
    [...host.querySelectorAll<HTMLElement>("button,[role=button]")].find(
      (b) => b.textContent === text || b.getAttribute("aria-label") === text,
    )!;
  return { dom, host, root, button };
}
const plugin = {
  id: "example",
  name: "Example",
  version: "1.0.0",
  source: "owner/plugin",
  status: "update",
  latest: "2.0.0",
  release_id: "v2",
  asset_id: "zip",
};

test("preview is bounded", () => {
  assert.equal(notesPreview("One\nTwo").more, false);
  assert.equal(notesPreview("One\nTwo\nThree\nFour").text, "One\nTwo\nThree");
  assert.ok(notesPreview("x".repeat(1000)).text.length <= 361);
});

test("notes are inert, collapsed; disclosure focus is stable and controller Back never installs", async () => {
  const f = setup();
  let installs = 0;
  let backs = 0;
  await act(async () =>
    f.root.render(
      createElement(ReleaseReview, {
        name: "Example",
        installed: "1",
        selected: "2",
        notes: {
          notes: "One\nTwo\nThree\n<script>alert(1)</script>",
          release_url: "https://github.com/owner/plugin/releases/tag/v2",
        },
        onBack: () => {
          backs++;
        },
        onContinue: () => {
          installs++;
        },
      }),
    ),
  );
  assert.equal(document.activeElement?.textContent?.trim(), "Back");
  assert.equal(installs, 0);
  assert.equal(f.button("View full release on GitHub"), undefined);
  assert.equal(f.host.querySelector("script"), null);
  const more = f.button("Show more");
  async function direction(button: number) {
    await act(async () =>
      document.activeElement?.dispatchEvent(
        new f.dom.window.CustomEvent("decky-direction", {
          detail: { button },
          bubbles: false,
          cancelable: true,
        }),
      ),
    );
  }
  // Steam dispatches direction events on controls; do not rely on DOM bubbling.
  await direction(10);
  assert.equal(document.activeElement, more);
  await direction(10);
  assert.equal(document.activeElement, f.button("Continue"));
  await direction(9);
  assert.equal(document.activeElement, more);
  await act(async () =>
    more.dispatchEvent(
      new f.dom.window.Event("decky-activate", { bubbles: true }),
    ),
  );
  assert.equal(more.getAttribute("aria-expanded"), "true");
  assert.equal(document.activeElement, more);
  assert.ok(f.host.textContent?.includes("<script>"));
  assert.equal(f.host.querySelector("script"), null);
  await act(async () => more.click());
  assert.equal(more.getAttribute("aria-expanded"), "false");
  await act(async () =>
    document.activeElement?.dispatchEvent(
      new f.dom.window.Event("decky-cancel", {
        bubbles: true,
        cancelable: true,
      }),
    ),
  );
  assert.equal(backs, 1);
  assert.equal(installs, 0);
  await act(async () => f.root.unmount());
});

test("missing and short notes are minimal and repeated activation stages only once", async () => {
  const f = setup();
  let calls = 0;
  let finish!: () => void;
  await act(async () =>
    f.root.render(
      createElement(ReleaseReview, {
        name: "Example",
        selected: "2",
        onBack: () => {},
        onContinue: () => {
          calls++;
          return new Promise<void>((resolve) => {
            finish = resolve;
          });
        },
      }),
    ),
  );
  assert.ok(f.host.textContent?.includes("No release notes provided"));
  assert.equal(f.button("Show more"), undefined);
  const next = f.button("Continue");
  await act(async () => {
    next.click();
    next.click();
  });
  assert.equal(calls, 1);
  assert.equal((next as HTMLButtonElement).disabled, true);
  await act(async () => finish());
  await act(async () => f.root.unmount());
});

test("manual selection reviews before staging; Back restores row and no extra catalogue load", async () => {
  const f = setup();
  let installs = 0;
  let loads = 0;
  let confirmed = false;
  const option = {
    release_id: "old",
    asset_id: "zip",
    tag: "0.9.0",
    version: "0.9.0",
    prerelease: false,
    installed: false,
    downgrade: true,
    installable: true,
    reason: null,
    release_notes: { notes: "Older fixes" },
  };
  await act(async () =>
    f.root.render(
      createElement(ReleaseSelector, {
        plugin,
        busy: false,
        load: async () => {
          loads++;
          return { releases: [option], next_cursor: null, error: null };
        },
        install: async (_, consent) => {
          installs++;
          confirmed = consent;
        },
        onBack: () => {},
      }),
    ),
  );
  const row = f.host.querySelector(".ddu-release") as HTMLElement;
  row.focus();
  const container = f.host.querySelector(".ddu-details") as HTMLElement;
  container.scrollTop = 87;
  await act(async () =>
    row.dispatchEvent(
      new f.dom.window.Event("decky-activate", { bubbles: true }),
    ),
  );
  assert.equal(installs, 0);
  assert.ok(f.button("Continue with downgrade"));
  await act(async () =>
    f.host.querySelector(".ddu-back:not([hidden])")?.dispatchEvent(
      new f.dom.window.Event("decky-cancel", {
        bubbles: true,
        cancelable: true,
      }),
    ),
  );
  assert.equal(installs, 0);
  assert.equal(loads, 1);
  assert.equal(document.activeElement, row);
  assert.equal(container.scrollTop, 87);
  await act(async () => row.click());
  await act(async () => f.button("Continue with downgrade").click());
  assert.equal(installs, 1);
  assert.equal(confirmed, true);
  await act(async () => f.root.unmount());
});

test("Plugin Details Update remains a review entry; notes never clutter details", async () => {
  const f = setup();
  let selected = false;
  let stages = 0;
  await act(async () =>
    f.root.render(
      createElement(PluginDetails, {
        plugin: { ...plugin, release_notes: { notes: "Hidden changelog" } },
        busy: false,
        checking: false,
        onBack: () => {},
        onUpdate: () => {
          selected = true;
        },
        onSearch: () => {},
        onVerify: () => {},
        onConfirm: () => {},
        onRetry: () => {},
        backRef: () => {},
        loadReleases: async () => ({
          releases: [],
          next_cursor: null,
          error: null,
        }),
        onInstallRelease: async () => {
          stages++;
        },
      }),
    ),
  );
  assert.ok(!f.host.textContent?.includes("Hidden changelog"));
  await act(async () => f.button("Update").click());
  assert.equal(selected, true);
  assert.equal(stages, 0);
  await act(async () => f.root.unmount());
});

test("list and details Update open review before RPC; Continue alone stages and uses security gate", async () => {
  const f = setup();
  Object.assign(globalThis, {
    getComputedStyle: f.dom.window.getComputedStyle.bind(f.dom.window),
  });
  Object.assign(globalThis, { releaseRpc: async () => [] });
  const { default: pluginFactory } = await import("../src/index");
  const instance = (pluginFactory as unknown as () => any)();
  const Content = instance.content.props.children.props.children.type;
  instance.onDismount();
  const { createUpdateStore } = await import("../src/updateStore");
  const { createFindStore } = await import("../src/findStore");
  let stages = 0;
  let security = 0;
  Object.assign(globalThis, {
    releaseRpc: async (name: string) => {
      if (name === "plugin_security") return null;
      if (name === "stage_update") {
        stages++;
        return { update: { name: "Example", version: "2.0.0" }, error: null };
      }
      throw new Error(name);
    },
  });
  const store = createUpdateStore({
    list: async () => [plugin],
    check: async () => [plugin],
    listen: () => () => {},
    schedule: () => () => {},
  });
  const finder = createFindStore(async () => ({ results: [] }));
  store.start();
  await store.refresh(false);
  await act(async () =>
    f.root.render(
      createElement(Content, {
        store,
        finder,
        finderActions: {
          install: async () => "",
          check: async () => false,
          cancel: async () => {},
        },
        securityInstaller: {
          request: async () => {
            security++;
            return { requested: true };
          },
        } as any,
      }),
    ),
  );
  const quick = f.host.querySelector(".ddu-quick-update") as HTMLElement;
  quick.focus();
  const list = f.host.querySelector(".ddu-list") as HTMLElement;
  list.scrollTop = 45;
  await act(async () => quick.click());
  assert.equal(stages, 0);
  assert.ok(f.button("Continue"));
  const review = f.button("Continue").closest(".ddu-details")!;
  await act(async () =>
    review.dispatchEvent(
      new f.dom.window.Event("decky-cancel", {
        bubbles: true,
        cancelable: true,
      }),
    ),
  );
  await new Promise((resolve) => f.dom.window.requestAnimationFrame(resolve));
  assert.equal(stages, 0);
  assert.equal(document.activeElement, quick);
  assert.equal(list.scrollTop, 45);
  await act(async () =>
    (f.host.querySelector(".ddu-plugin-details") as HTMLElement).click(),
  );
  await act(async () => f.button("Update").click());
  assert.equal(stages, 0);
  await act(async () => f.button("Continue").click());
  assert.equal(stages, 1);
  assert.equal(security, 1);
  await act(async () => f.root.unmount());
  store.dispose();
  finder.dispose();
});
