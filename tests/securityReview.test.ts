import assert from "node:assert/strict";
import { test } from "node:test";
import { registerHooks } from "node:module";
import { JSDOM } from "jsdom";
import { createElement, act } from "react";
import { createRoot } from "react-dom/client";
import {
  createSecurityInstaller,
  type SecurityAssessment,
} from "../src/securityInstaller";
import type { StagedUpdate } from "../src/deckyInstaller";

registerHooks({
  resolve(specifier, context, next) {
    if (specifier === "@decky/ui")
      return {
        url: new URL("./mocks/decky-ui.mjs", import.meta.url).href,
        shortCircuit: true,
      };
    return next(specifier, context);
  },
});
const { SecurityReviewBoundary } = await import("../src/SecurityReview");
export const rootAssessment: SecurityAssessment = {
  root_requested: true,
  flags: ["root"],
  has_python_backend: true,
  external_binaries: [],
  previous_root_requested: false,
  previous_has_python_backend: true,
  previous_external_binaries: [],
  added_binary_names: [],
  changed_binary_source_hosts: [],
  comparison_available: true,
  updating: true,
  requires_acknowledgment: true,
  findings: [{ kind: "root_added", severity: "warning" }],
};
function staged(token = "one", security = rootAssessment): StagedUpdate {
  return {
    artifact: "file:///tmp/staged/update-one.zip",
    name: "Example",
    version: "2.0.0",
    previous_version: "1.0.0",
    hash: "a".repeat(64),
    review_token: token,
    security,
  };
}
function setup(nativeFocus?: () => void) {
  let native = 0;
  let authorizations = 0;
  const discarded: string[] = [];
  let selected = staged();
  const installer = createSecurityInstaller({
    authorize: async (token, acknowledged) => {
      authorizations++;
      assert.equal(token, selected.review_token);
      assert.equal(acknowledged, selected.security!.requires_acknowledgment);
      return {
        update: { ...selected, security_authorized: true },
        error: null,
      };
    },
    discard: async (token) => {
      discarded.push(token);
    },
    request: async () => {
      native++;
      nativeFocus?.();
      return { requested: true };
    },
  });
  return {
    installer,
    discarded,
    selected,
    select: (value: StagedUpdate) => {
      selected = value;
    },
    native: () => native,
    authorizations: () => authorizations,
  };
}

test("controller review starts on Cancel, blocks repeated A, restores origin and scroll on B", async () => {
  const dom = new JSDOM("<div id='root'></div>", { pretendToBeVisual: true });
  Object.assign(globalThis, {
    window: dom.window,
    document: dom.window.document,
    HTMLElement: dom.window.HTMLElement,
    requestAnimationFrame: dom.window.requestAnimationFrame.bind(dom.window),
    cancelAnimationFrame: dom.window.cancelAnimationFrame.bind(dom.window),
    IS_REACT_ACT_ENVIRONMENT: true,
  });
  const nativeButton = document.createElement("button");
  nativeButton.textContent = "Native confirmation";
  document.body.append(nativeButton);
  const f = setup(() => nativeButton.focus());
  const element = document.getElementById("root")!;
  const root = createRoot(element);
  await act(async () => {
    root.render(
      createElement(SecurityReviewBoundary, {
        installer: f.installer,
        children: createElement(
          "div",
          { id: "list" },
          createElement("button", { id: "origin" }, "Update"),
        ),
      }),
    );
  });
  const origin = document.getElementById("origin")!;
  origin.focus();
  const list = document.getElementById("list")!;
  list.scrollTop = 120;
  let result!: Promise<unknown>;
  await act(async () => {
    result = f.installer.request(f.selected);
  });
  const dialog = document.querySelector('[role="alertdialog"]')!;
  assert.equal(document.activeElement?.textContent, "Cancel");
  assert.equal(
    document.activeElement?.closest(".ddu-security-actions") !== null,
    true,
  );
  assert.ok(dialog.textContent?.includes("Example · 1.0.0 → 2.0.0"));
  assert.ok(
    dialog.textContent?.includes("It can modify SteamOS files and settings."),
  );
  assert.equal(dialog.textContent?.includes("Python backend included"), false);
  const disclosure = dialog.querySelector("[aria-expanded]")!;
  const move = async (button: number) => {
    await act(async () => {
      document.activeElement!.dispatchEvent(
        new dom.window.CustomEvent("decky-direction", {
          detail: { button },
          bubbles: true,
          cancelable: true,
        }),
      );
    });
  };
  await move(12);
  assert.equal(
    document.activeElement?.textContent,
    "Cancel",
    "disabled Continue cannot receive controller focus",
  );
  // Native DialogButton handles direction at the button; it need not bubble to the group.
  await move(9);
  assert.equal(document.activeElement?.getAttribute("role"), "checkbox");
  assert.equal(document.activeElement?.getAttribute("aria-checked"), "false");
  await move(9);
  assert.equal(document.activeElement, disclosure);
  (dialog.querySelector('[role="heading"]') as HTMLElement).focus();
  // Steam changes inactive native Focusables to tabindex=-1 in the QAM.
  disclosure.setAttribute("tabindex", "-1");
  dialog.querySelector('[role="checkbox"]')!.setAttribute("tabindex", "-1");
  await move(10);
  assert.equal(document.activeElement, disclosure);
  await move(10);
  assert.equal(document.activeElement?.getAttribute("role"), "checkbox");
  await move(10);
  assert.equal(
    document.activeElement?.textContent,
    "Cancel",
    "skip disabled confirmation and navigation-only wrappers",
  );
  await move(9);
  assert.equal(document.activeElement?.getAttribute("role"), "checkbox");
  assert.equal(f.native(), 0);

  assert.equal(disclosure.tagName, "DIV");
  assert.equal(disclosure.getAttribute("aria-expanded"), "false");
  await act(async () => {
    (disclosure as HTMLElement).click();
  });
  assert.equal(disclosure.getAttribute("aria-expanded"), "true");
  assert.ok(document.getElementById(disclosure.getAttribute("aria-controls")!));
  await act(async () => {
    disclosure.dispatchEvent(
      new dom.window.CustomEvent("decky-activate", { bubbles: true }),
    );
  });
  assert.equal(disclosure.getAttribute("aria-expanded"), "false");

  const buttons = [...dialog.querySelectorAll("button")];
  const next = buttons.find((button) => button.textContent === "Continue")!;
  assert.equal(next.disabled, true);
  await act(async () => {
    next.click();
    f.installer.continue("one");
    f.installer.continue("one");
  });
  assert.equal(f.native(), 0);
  assert.equal(f.authorizations(), 0);
  await act(async () => {
    dialog.dispatchEvent(
      new dom.window.CustomEvent("decky-cancel", {
        bubbles: true,
        cancelable: true,
      }),
    );
    await result;
  });
  await act(async () => {
    await new Promise((resolve) => setTimeout(resolve, 25));
  });
  assert.equal(document.querySelector('[role="alertdialog"]'), null);
  assert.equal(document.activeElement, origin);
  assert.equal(list.scrollTop, 120);
  assert.deepEqual(f.discarded, ["one"]);
  // Reopening never remembers a previous checkbox; controller A on Cancel cannot approve.
  await act(async () => {
    result = f.installer.request(f.selected);
  });
  await act(async () => {
    document.activeElement!.dispatchEvent(
      new dom.window.CustomEvent("decky-activate", { bubbles: true }),
    );
    await result;
  });
  assert.equal(f.native(), 0);
  await act(async () => {
    result = f.installer.request(f.selected);
  });
  const checkbox = document.querySelector('[role="checkbox"]')!;
  assert.equal(checkbox.getAttribute("aria-checked"), "false");
  for (const key of [" ", "Enter"]) {
    await act(async () => {
      checkbox.dispatchEvent(
        new dom.window.KeyboardEvent("keydown", {
          key,
          bubbles: true,
          cancelable: true,
        }),
      );
    });
  }
  assert.equal(
    document.querySelector('[role="checkbox"]')?.getAttribute("aria-checked"),
    "false",
  );
  await act(async () => {
    (checkbox as HTMLElement).click();
  });
  assert.equal(
    document.querySelector('[role="checkbox"]')?.getAttribute("aria-checked"),
    "true",
  );
  await act(async () => {
    (checkbox as HTMLElement).click();
  });

  await act(async () => {
    checkbox.dispatchEvent(
      new dom.window.CustomEvent("decky-activate", { bubbles: true }),
    );
  });
  assert.equal(
    document.querySelector('[role="checkbox"]')?.getAttribute("aria-checked"),
    "true",
  );
  const continueButton = [...document.querySelectorAll("button")].find(
    (b) => b.textContent === "Continue",
  )!;
  assert.equal(continueButton.disabled, false);
  const cancelButton = document.querySelector(
    ".ddu-security-actions button",
  ) as HTMLButtonElement;
  cancelButton.focus();
  await move(12);
  assert.equal(document.activeElement, continueButton);
  await move(11);
  assert.equal(document.activeElement, cancelButton);
  await act(async () => {
    cancelButton.dispatchEvent(
      new dom.window.KeyboardEvent("keydown", {
        key: "ArrowRight",
        bubbles: true,
        cancelable: true,
      }),
    );
  });
  assert.equal(document.activeElement, continueButton);
  await act(async () => {
    continueButton.dispatchEvent(
      new dom.window.KeyboardEvent("keydown", {
        key: "ArrowLeft",
        bubbles: true,
        cancelable: true,
      }),
    );
  });
  assert.equal(document.activeElement, cancelButton);
  assert.equal(f.native(), 0, "moving focus must not confirm installation");
  await act(async () => {
    continueButton.click();
    continueButton.click();
    await result;
  });
  assert.equal(f.native(), 1);
  assert.equal(f.authorizations(), 1);
  await act(async () => {
    await new Promise((resolve) => setTimeout(resolve, 25));
  });
  assert.equal(
    document.activeElement,
    nativeButton,
    "restoration must not steal focus from Decky confirmation",
  );
  await act(async () => {
    result = f.installer.request(f.selected);
  });
  await act(async () => {
    document.querySelector('[role="alertdialog"]')!.dispatchEvent(
      new dom.window.KeyboardEvent("keydown", {
        key: "Escape",
        bubbles: true,
        cancelable: true,
      }),
    );
    await result;
  });
  assert.equal(f.native(), 1);
  f.select(staged("unmounted"));
  await act(async () => {
    result = f.installer.request(staged("unmounted"));
  });
  await act(async () => {
    root.unmount();
    await result;
  });
  assert.equal(f.native(), 1);
  assert.equal(f.discarded.at(-1), "unmounted");
  dom.window.close();
});

test("routine packages skip review; changed artifacts and wrong acknowledgments cannot approve another release", async () => {
  const f = setup();
  let result = f.installer.request(f.selected);
  f.installer.acknowledge("different", true);
  f.installer.continue("one");
  assert.equal(f.authorizations(), 0);
  f.installer.acknowledge("one", true);
  f.installer.cancel("one");
  await result;
  const second = {
    ...staged("two"),
    name: "Other plugin",
    hash: "b".repeat(64),
    version: "3.0.0",
  };
  f.select(second);
  result = f.installer.request(second);
  assert.equal(f.installer.getSnapshot()?.acknowledged, false);
  f.installer.continue("one");
  assert.equal(f.authorizations(), 0);
  f.installer.cancel("two");
  await result;
  const ordinary = staged("ordinary", {
    ...rootAssessment,
    root_requested: false,
    flags: [],
    requires_acknowledgment: false,
    findings: [],
  });
  f.select(ordinary);
  assert.equal((await f.installer.request(ordinary)).requested, true);
  assert.equal(f.installer.getSnapshot(), null);
  assert.equal(f.native(), 1);
});

test("concurrent install and unmount cannot approve or leave a pending review", async () => {
  const f = setup();
  const first = f.installer.request(f.selected);
  assert.equal((await f.installer.request(staged("second"))).requested, false);
  f.installer.dispose();
  assert.equal((await first).requested, false);
  assert.equal(f.native(), 0);
  assert.deepEqual(f.discarded, ["second", "one"]);
});

test("authorization mismatch, missing facts and native failure all stop and discard", async () => {
  const packageToInstall = staged("ordinary", {
    ...rootAssessment,
    requires_acknowledgment: false,
  });
  for (const mismatch of [
    "hash",
    "name",
    "version",
    "artifact",
    "review_token",
    "security_authorized",
    "native",
  ] as const) {
    let calls = 0;
    const discarded: string[] = [];
    const installer = createSecurityInstaller({
      authorize: async () => ({
        update: {
          ...packageToInstall,
          security_authorized: true,
          ...(mismatch === "native"
            ? {}
            : {
                [mismatch]:
                  mismatch === "security_authorized" ? false : "changed",
              }),
        } as StagedUpdate,
        error: null,
      }),
      discard: async (token) => {
        discarded.push(token);
      },
      request: async () => {
        calls++;
        return { requested: false };
      },
    });
    assert.equal((await installer.request(packageToInstall)).requested, false);
    assert.equal(calls, mismatch === "native" ? 1 : 0);
    assert.deepEqual(discarded, ["ordinary"]);
  }
  const f = setup();
  assert.equal(
    (await f.installer.request({ ...f.selected, security: undefined }))
      .requested,
    false,
  );
  assert.equal(f.native(), 0);
  assert.deepEqual(f.discarded, ["one"]);
});

test("Find Plugins cancellation invalidates its ticket without a native request or association", async () => {
  const { createFindInstaller } = await import("../src/findInstaller");
  const f = setup();
  const finished: boolean[] = [];
  let saved = false;
  const finder = createFindInstaller({
    stage: async () => ({ ...f.selected, ticket: "find-ticket" }),
    finish: async (_, cancelled) => {
      finished.push(cancelled);
      return { installed: false };
    },
    request: f.installer.request,
    refresh: async () => {},
    installed: () => {
      saved = true;
    },
  });
  const selection = {
    repository: "owner/repo",
    name: "Example",
    owner: "owner",
    stars: 1,
    description: "",
    fork: false,
    archived: false,
    disabled: false,
    status: "install",
    token: "selected",
    release_id: 1,
    asset_id: 2,
  };
  const work = finder.install(selection);
  await Promise.resolve();
  f.installer.cancel("one");
  assert.match(await work, /cancelled/);
  assert.deepEqual(finished, [true]);
  assert.equal(f.native(), 0);
  assert.equal(saved, false);
  assert.equal(await finder.check(), false);
});

test("installed details show four concise points and a subdued native uninstall action at the end", async () => {
  const { PluginDetails } = await import("../src/PluginDetails");
  const dom = new JSDOM("<div id='root'></div>", { pretendToBeVisual: true });
  Object.assign(globalThis, {
    window: dom.window,
    document: dom.window.document,
    HTMLElement: dom.window.HTMLElement,
    IS_REACT_ACT_ENVIRONMENT: true,
  });
  const prompts: string[][] = [];
  Object.assign(dom.window, {
    DeckyPluginLoader: {
      uninstallPlugin: (...args: string[]) => prompts.push(args),
    },
  });
  const root = createRoot(document.getElementById("root")!);
  const noop = () => {};
  await act(async () => {
    root.render(
      createElement(PluginDetails, {
        canUninstall: true,
        plugin: {
          id: "example",
          name: "Example",
          version: "1.0.0",
          source: "owner/example",
          status: "current",
          security: rootAssessment,
        },
        busy: false,
        checking: false,
        onBack: noop,
        onUpdate: noop,
        onSearch: noop,
        onVerify: noop,
        onConfirm: noop,
        onRetry: noop,
        backRef: noop,
        loadReleases: async () => ({
          releases: [],
          next_cursor: null,
          error: null,
        }),
        onInstallRelease: async () => {},
      }),
    );
  });
  const disclosure = document.querySelector("[aria-expanded]") as HTMLElement;
  await act(async () => {
    disclosure.click();
  });
  assert.equal(
    document.querySelectorAll(".ddu-security-summary > li").length,
    4,
  );
  assert.equal(
    document
      .querySelector(".ddu-security-summary")
      ?.textContent?.includes("Python backend included"),
    true,
  );
  assert.equal(
    document.body.textContent?.includes("This is a manifest review"),
    false,
  );
  assert.equal(
    document.body.textContent?.includes("The selected ZIP is inspected"),
    false,
  );
  const actions = [...document.querySelectorAll(".ddu-actions button")];
  const last = actions.at(-1) as HTMLButtonElement;
  assert.equal(last.textContent, "Uninstall");
  assert.equal(last.classList.contains("ddu-uninstall"), true);
  assert.equal(actions.at(-2)?.textContent, "Change source");
  assert.equal(prompts.length, 0);
  await act(async () => {
    last.click();
  });
  assert.equal(prompts.length, 1);
  assert.equal(prompts[0][0], "Example");
  await act(async () => root.unmount());
  dom.window.close();
});

test("Find Plugins shows download feedback immediately and prevents repeated installs", async () => {
  const { FindPlugins } = await import("../src/FindPlugins");
  const { createFindStore } = await import("../src/findStore");
  const dom = new JSDOM("<div id='root'></div>", { pretendToBeVisual: true });
  Object.assign(globalThis, {
    window: dom.window,
    document: dom.window.document,
    HTMLElement: dom.window.HTMLElement,
    IS_REACT_ACT_ENVIRONMENT: true,
  });
  const selection = {
    repository: "owner/example",
    name: "Example",
    owner: "owner",
    stars: 1,
    description: "",
    fork: false,
    archived: false,
    disabled: false,
    status: "install",
    token: "example",
    release_id: 1,
    asset_id: 2,
  };
  const store = createFindStore(async () => ({
    results: [selection],
    direct: true,
  }));
  store.type("owner/example");
  await store.submit();
  let finish!: (message: string) => void;
  const pending = new Promise<string>((resolve) => {
    finish = resolve;
  });
  let calls = 0;
  const root = createRoot(document.getElementById("root")!);
  await act(async () => {
    root.render(
      createElement(FindPlugins, {
        open: true,
        store,
        onBack: () => {},
        details: async () => selection,
        install: async () => {
          calls++;
          return pending;
        },
        checkInstallation: async () => false,
        cancelInstallation: async () => {},
      }),
    );
  });
  const button = [...document.querySelectorAll("button")].find(
    (b) => b.textContent === "Install",
  )!;

  const down = async (buttonCode: number) => {
    await act(async () => {
      document.activeElement!.dispatchEvent(
        new dom.window.CustomEvent("decky-direction", {
          detail: { button: buttonCode },
          bubbles: true,
          cancelable: true,
        }),
      );
    });
  };
  assert.equal(document.activeElement?.textContent?.includes("Back"), true);
  await down(10);
  assert.equal(
    document.activeElement,
    button,
    "one Down enters the result's Install button",
  );
  await down(10);
  assert.equal(document.activeElement?.textContent, "View on GitHub");
  await down(9);
  assert.equal(document.activeElement, button);
  await act(async () => {
    button.click();
    button.click();
  });
  assert.equal(calls, 1);
  assert.equal(button.disabled, true);
  assert.equal(button.getAttribute("aria-busy"), "true");
  assert.equal(button.textContent, "Preparing…");
  assert.equal(
    document.querySelector(".ddu-install-status")?.textContent,
    "Downloading and checking ZIP…",
  );
  await act(async () => {
    finish("Installation cancelled.");
    await pending;
  });
  assert.equal(button.textContent, "Install");
  assert.equal(button.disabled, false);
  assert.equal(document.querySelector(".ddu-install-status"), null);
  await act(async () => root.unmount());
  store.dispose();
  dom.window.close();
});

test("QAM navigation reads the portal document, skipping Steam's CSS-disabled buttons", async () => {
  const { useControllerNavigation } =
    await import("../src/useControllerNavigation");
  const shared = new JSDOM("<body></body>");
  const qam = new JSDOM(
    `<div id="panel"><button id="back">Back</button><div hidden><button>Hidden search</button></div><button id="disabled" class="Disabled">Unavailable</button><button id="install">Install</button><button id="github">GitHub</button></div>`,
  );
  Object.assign(globalThis, {
    window: shared.window,
    document: shared.window.document,
    HTMLElement: shared.window.HTMLElement,
  });
  const ui = qam.window.document;
  const root = ui.getElementById("panel")!;
  const navigation = useControllerNavigation({ current: root });
  ui.getElementById("back")!.focus();
  assert.equal(document.activeElement, document.body);
  assert.notEqual(ui.activeElement, document.activeElement);
  assert.equal(
    (ui.getElementById("disabled") as HTMLButtonElement).disabled,
    false,
  );
  const down = new qam.window.CustomEvent("decky-direction", {
    detail: { button: 10 },
    cancelable: true,
  });
  navigation.onGamepadDirection(down);
  assert.equal(down.defaultPrevented, true);
  assert.equal(ui.activeElement, ui.getElementById("install"));
  navigation.onGamepadDirection(
    new qam.window.CustomEvent("decky-direction", {
      detail: { button: 10 },
      cancelable: true,
    }),
  );
  assert.equal(ui.activeElement, ui.getElementById("github"));
  navigation.onGamepadDirection(
    new qam.window.CustomEvent("decky-direction", {
      detail: { button: 9 },
      cancelable: true,
    }),
  );
  assert.equal(ui.activeElement, ui.getElementById("install"));
  shared.window.close();
  qam.window.close();
});

test("security review restores focus across the SharedJSContext and Quick Access documents", async () => {
  const { createPortal } = await import("react-dom");
  const shared = new JSDOM("<div id='root'></div>", {
    pretendToBeVisual: true,
  });
  const qam = new JSDOM("<div id='qam'></div>", { pretendToBeVisual: true });
  Object.assign(globalThis, {
    window: shared.window,
    document: shared.window.document,
    HTMLElement: shared.window.HTMLElement,
    requestAnimationFrame: shared.window.requestAnimationFrame.bind(
      shared.window,
    ),
    cancelAnimationFrame: shared.window.cancelAnimationFrame.bind(
      shared.window,
    ),
    IS_REACT_ACT_ENVIRONMENT: true,
  });
  const f = setup();
  const root = createRoot(document.getElementById("root")!);
  await act(async () => {
    root.render(
      createPortal(
        createElement(SecurityReviewBoundary, {
          installer: f.installer,
          children: createElement(
            "button",
            { id: "portal-install" },
            "Install",
          ),
        }),
        qam.window.document.getElementById("qam")!,
      ),
    );
  });
  const origin = qam.window.document.getElementById("portal-install")!;
  origin.focus();
  let result!: Promise<unknown>;
  await act(async () => {
    result = f.installer.request(f.selected);
  });
  assert.equal(qam.window.document.activeElement?.textContent, "Cancel");
  await act(async () => {
    qam.window.document.querySelector('[role="alertdialog"]')!.dispatchEvent(
      new qam.window.CustomEvent("decky-cancel", {
        bubbles: true,
        cancelable: true,
      }),
    );
    await result;
  });
  await act(async () => {
    await new Promise((resolve) => setTimeout(resolve, 25));
  });
  assert.equal(qam.window.document.activeElement, origin);
  assert.equal(f.native(), 0);
  await act(async () => root.unmount());
  shared.window.close();
  qam.window.close();
});

test("Find Plugins translates backend compatibility errors into the Steam UI language", async () => {
  const { FindPlugins } = await import("../src/FindPlugins");
  const { createFindStore } = await import("../src/findStore");
  const { LanguageProvider } = await import("../src/i18n");
  const previousSteam = (globalThis as unknown as { SteamClient?: unknown })
    .SteamClient;
  const dom = new JSDOM("<div id='root'></div>", { pretendToBeVisual: true });
  Object.assign(globalThis, {
    window: dom.window,
    document: dom.window.document,
    HTMLElement: dom.window.HTMLElement,
    IS_REACT_ACT_ENVIRONMENT: true,
    SteamClient: { Settings: { GetCurrentLanguage: async () => "spanish" } },
  });
  const row = {
    repository: "ValentineBSAA/ResonaDeck",
    name: "ResonaDeck",
    owner: "ValentineBSAA",
    stars: 1,
    description: "",
    fork: false,
    archived: false,
    disabled: false,
  };
  const store = createFindStore(async () => ({ results: [row], direct: true }));
  store.type(row.repository);
  await store.submit();
  const root = createRoot(document.getElementById("root")!);
  try {
    await act(async () => {
      root.render(
        createElement(LanguageProvider, {
          children: createElement(FindPlugins, {
            open: true,
            store,
            onBack() {},
            details: async () => ({
              ...row,
              status: "unavailable",
              error: "No compatible Decky release found.",
            }),
            install: async () => {
              assert.fail("incompatible result must not install");
            },
            checkInstallation: async () => false,
            cancelInstallation: async () => {},
          }),
        }),
      );
    });
    assert.ok(
      document.body.textContent?.includes(
        "No se ha podido identificar un ZIP instalable de Decky.",
      ),
    );
    assert.equal(
      document.body.textContent?.includes("No compatible Decky release found."),
      false,
    );
  } finally {
    await act(async () => root.unmount());
    dom.window.close();
    Object.assign(globalThis, { SteamClient: previousSteam });
  }
});
