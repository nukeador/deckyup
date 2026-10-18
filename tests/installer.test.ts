import assert from "node:assert/strict";
import { test } from "node:test";
import {
  requestUpdate,
  requestSelfUpdate,
  reopenAfterSelfUpdate,
  selfUpdatePanel,
  type Router,
} from "../src/deckyInstaller";

function loaderPanelFixture(version: string) {
  type Plugin = { name: string; version: string; content: object };
  const replacement: Plugin = {
    name: "Decky Direct Updater",
    version,
    content: {},
  };
  const plugins = [replacement];
  const deckyState = {
    activePlugin: {
      ...replacement,
      version: "previous",
      content: {},
    } as Plugin | null,
    closeActivePlugin() {
      this.activePlugin = null;
    },
    setActivePlugin(name: string) {
      this.activePlugin =
        plugins.find((plugin) => plugin.name === name) ?? null;
    },
  };
  return { plugins, deckyState };
}

const update = {
  security_authorized: true,
  artifact:
    "file:///home/deck/homebrew/data/decky-direct-updater/staged/update-abcd.zip",
  name: "MAKO - Frame Generation",
  version: "4.5.0",
  hash: "a".repeat(64),
};
test("requests the native prompt with exact identity, local file, checksum and UPDATE mode", async () => {
  let args: unknown[] = [];
  const router: Router = {
    call: async (...values) => {
      args = values;
    },
  };
  assert.deepEqual(await requestUpdate(update, router), { requested: true });
  assert.deepEqual(args, [
    "utilities/install_plugin",
    update.artifact,
    update.name,
    update.version,
    update.hash,
    2,
  ]);
  assert.equal("installed" in (await requestUpdate(update, router)), false);
});
test("missing API offers manual ZIP fallback", async () => {
  const result = await requestUpdate(update);
  assert.equal(result.requested, false);
  assert.match(result.error!, /Install Plugin from ZIP/);
});
test("API rejection and failure do not report installation", async () => {
  for (const router of [
    { call: async () => false },
    { call: async () => ({ success: false }) },
    {
      call: async () => {
        throw new Error("unsupported route");
      },
    },
  ]) {
    assert.equal((await requestUpdate(update, router)).requested, false);
  }
});
test("rejects remote or unstaged artifacts and invalid hashes", async () => {
  const router: Router = {
    call: async () => {
      throw new Error("must not be called");
    },
  };
  for (const value of [
    { ...update, artifact: "https://github.com/x/y/release.zip" },
    { ...update, artifact: "file:///etc/passwd" },
    { ...update, hash: "invalid" },
  ]) {
    assert.match((await requestUpdate(value, router)).error!, /Invalid staged/);
  }
});

test("manual downgrade requests Decky's DOWNGRADE prompt and never claims completion", async () => {
  let args: unknown[] = [];
  const result = await requestUpdate(
    { ...update, install_type: "downgrade" },
    {
      call: async (...values) => {
        args = values;
      },
    },
  );
  assert.equal(args.at(-1), 3);
  assert.deepEqual(result, { requested: true });
  assert.equal("installed" in result, false);
});

test("new installations reuse validated staging and request native INSTALL mode", async () => {
  let args: unknown[] = [];
  const result = await requestUpdate(
    { ...update, install_type: "install" },
    {
      call: async (...values) => {
        args = values;
      },
    },
  );
  assert.equal(args.at(-1), 0);
  assert.deepEqual(result, { requested: true });
});

test("Loader completion event subscription is isolated and removable", async () => {
  const { listenForInstallCompletion } = await import("../src/deckyInstaller");
  let listener: ((...args: unknown[]) => void) | undefined;
  let completions = 0;
  let removed = false;
  const stop = listenForInstallCompletion(
    () => {
      completions++;
    },
    {
      call: async () => {},
      addEventListener(event, fn) {
        assert.equal(event, "loader/plugin_download_finish");
        listener = fn;
      },
      removeEventListener(event, fn) {
        assert.equal(event, "loader/plugin_download_finish");
        assert.equal(listener, fn);
        removed = true;
      },
    },
  );
  listener!("plugin");
  assert.equal(completions, 1);
  stop();
  assert.equal(removed, true);
  listenForInstallCompletion(
    () => {
      throw Error("unavailable");
    },
    { call: async () => {} },
  )();
});

test("self-update reopens Decky only when installed version matches", async () => {
  const values = new Map<string, string>();
  const previous = globalThis.window;
  Object.defineProperty(globalThis, "window", {
    configurable: true,
    value: {
      DeckyPluginLoader: loaderPanelFixture(update.version),
      sessionStorage: {
        getItem: (key: string) => values.get(key) ?? null,
        setItem: (key: string, value: string) => {
          values.set(key, value);
        },
        removeItem: (key: string) => {
          values.delete(key);
        },
      },
    },
  });
  try {
    const self = { ...update, name: "Decky Direct Updater" };
    let closed = 0;
    const navigation = {
      CloseSideMenus: () => {
        closed++;
      },
      OpenQuickAccessMenu: (_tab: number) => {},
    };
    await requestSelfUpdate(self, async () => ({ requested: true }));
    await reopenAfterSelfUpdate(
      async () => [{ name: self.name, version: "old" }],
      navigation,
      { version: self.version, instance: "replacement" },
    );
    assert.equal(closed, 0);
    await reopenAfterSelfUpdate(
      async () => [{ name: self.name, version: self.version }],
      navigation,
      { version: self.version, instance: "replacement" },
    );
    assert.equal(closed, 1);
    await new Promise((resolve) => setTimeout(resolve, 120));
    await reopenAfterSelfUpdate(
      async () => [{ name: self.name, version: self.version }],
      navigation,
      { version: self.version, instance: "replacement" },
    );
    assert.equal(closed, 1);
    await requestSelfUpdate(self, async () => ({ requested: false }));
    await reopenAfterSelfUpdate(
      async () => [{ name: self.name, version: self.version }],
      navigation,
      { version: self.version, instance: "replacement" },
    );
    assert.equal(closed, 1);
  } finally {
    if (previous === undefined)
      delete (globalThis as { window?: Window }).window;
    else
      Object.defineProperty(globalThis, "window", {
        configurable: true,
        value: previous,
      });
  }
});

test("native adapter rejects packages without backend review authorization", async () => {
  let called = false;
  const result = await requestUpdate(
    { ...update, security_authorized: false },
    {
      call: async () => {
        called = true;
      },
    },
  );
  assert.equal(result.requested, false);
  assert.equal(called, false);
});

test("uninstall delegates only to Loader's own confirmation dialog", async () => {
  const { requestUninstallConfirmation } =
    await import("../src/deckyInstaller");
  const text = {
    title: "Uninstall Example",
    button: "Uninstall",
    description: "Confirm removal?",
  };
  let args: string[] = [];
  const loader = {
    uninstallPlugin(...values: string[]) {
      assert.equal(this, loader);
      args = values;
    },
  };
  assert.deepEqual(
    requestUninstallConfirmation("Exact plugin name", text, loader),
    { requested: true },
  );
  assert.deepEqual(args, [
    "Exact plugin name",
    text.title,
    text.button,
    text.description,
  ]);
  assert.equal(
    requestUninstallConfirmation("Exact plugin name", text, undefined)
      .requested,
    false,
  );
  assert.equal(
    requestUninstallConfirmation("Exact plugin name", text, {
      uninstallPlugin() {
        throw new Error("unavailable");
      },
    }).requested,
    false,
  );
});

test("self-update ignores the old frontend even after files change, and preserves the handoff across unmounts", async () => {
  const previous = globalThis.window;
  const values = new Map<string, string>();
  const storage = {
    getItem: (key: string) => values.get(key) ?? null,
    setItem: (key: string, value: string) => {
      values.set(key, value);
    },
    removeItem: (key: string) => {
      values.delete(key);
    },
  };
  Object.defineProperty(globalThis, "window", {
    configurable: true,
    value: {
      sessionStorage: storage,
      DeckyPluginLoader: loaderPanelFixture("0.2.1"),
    },
  });
  try {
    const self = { ...update, name: "Decky Direct Updater", version: "0.2.1" };
    const oldFrontend = { version: "0.2.0", instance: "old" };
    const replacement = { version: self.version, instance: "new" };
    let closed = 0;
    let opened = 0;
    const navigation = {
      CloseSideMenus: () => {
        closed++;
      },
      OpenQuickAccessMenu: () => {
        opened++;
      },
    };
    const installed = async () => [{ name: self.name, version: self.version }];
    await requestSelfUpdate(
      self,
      async () => ({ requested: true }),
      oldFrontend,
    );
    const marker = [...values.values()][0];
    await reopenAfterSelfUpdate(installed, navigation, oldFrontend);
    assert.equal(
      closed,
      0,
      "new files do not prove the new frontend is running",
    );
    assert.equal([...values.values()][0], marker);
    await reopenAfterSelfUpdate(installed, navigation, {
      version: self.version,
      instance: "old",
    });
    assert.equal(
      closed,
      0,
      "the requesting instance cannot reopen even on same-version reinstall",
    );
    let finish!: (plugins: { name: string; version: string }[]) => void;
    let active = true;
    const checking = reopenAfterSelfUpdate(
      () =>
        new Promise((resolve) => {
          finish = resolve;
        }),
      navigation,
      replacement,
      () => active,
    );
    active = false;
    finish(await installed());
    await checking;
    assert.equal(closed, 0);
    assert.equal(
      [...values.values()][0],
      marker,
      "unmount during inventory must not consume the marker",
    );
    active = true;
    await reopenAfterSelfUpdate(
      installed,
      navigation,
      replacement,
      () => active,
    );
    assert.equal(closed, 1);
    assert.equal(
      values.size,
      1,
      "handoff remains pending until the replacement is selected",
    );
    active = false;
    await new Promise((resolve) => setTimeout(resolve, 120));
    assert.equal(opened, 0, "a disposed replacement must not reopen later");
    await requestSelfUpdate(
      self,
      async () => ({ requested: true }),
      oldFrontend,
    );
    await reopenAfterSelfUpdate(installed, navigation, replacement);
    await new Promise((resolve) => setTimeout(resolve, 120));
    assert.equal(opened, 1);
    await reopenAfterSelfUpdate(installed, navigation, replacement);
    assert.equal(closed, 2, "the completed handoff is consumed only once");
  } finally {
    if (previous === undefined)
      delete (globalThis as { window?: Window }).window;
    else
      Object.defineProperty(globalThis, "window", {
        configurable: true,
        value: previous,
      });
  }
});

test("self-update discards malformed or expired markers without polling inventory", async () => {
  const previous = globalThis.window;
  let raw: string | null = null;
  Object.defineProperty(globalThis, "window", {
    configurable: true,
    value: {
      sessionStorage: {
        getItem: () => raw,
        removeItem: () => {
          raw = null;
        },
      },
    },
  });
  try {
    const now = Date.now();
    for (const marker of [
      "invalid JSON",
      "null",
      "[]",
      "42",
      JSON.stringify({ version: "0.2.2" }),
      JSON.stringify({ version: "", created: now }),
      JSON.stringify({ version: "0.2.2", created: now, requester: 12 }),
      '{"version":"0.2.2","created":1e400}',
      JSON.stringify({ version: "0.2.2", created: now - 31 * 60 * 1000 }),
      JSON.stringify({ version: "0.2.2", created: now + 60_000 }),
    ]) {
      raw = marker;
      await reopenAfterSelfUpdate(
        async () => {
          assert.fail("invalid marker must not poll inventory");
        },
        {
          CloseSideMenus: () => assert.fail("must not close QAM"),
          OpenQuickAccessMenu: () => assert.fail("must not open QAM"),
        },
        { version: "0.2.2", instance: "replacement" },
      );
      assert.equal(raw, null, marker);
    }
  } finally {
    if (previous === undefined)
      delete (globalThis as { window?: Window }).window;
    else
      Object.defineProperty(globalThis, "window", {
        configurable: true,
        value: previous,
      });
  }
});

test("self-update replaces Loader's cached active plugin only when the target is registered", () => {
  const loader = loaderPanelFixture("0.2.2");
  const stale = loader.deckyState.activePlugin;
  assert.notEqual(stale, loader.plugins[0]);
  assert.equal(selfUpdatePanel("0.2.1", loader), null);
  const panel = selfUpdatePanel("0.2.2", loader)!;
  assert.equal(panel.close(), true);
  assert.equal(
    loader.deckyState.activePlugin,
    null,
    "clear old content before selecting the new instance",
  );
  assert.equal(panel.select(), true);
  assert.equal(loader.deckyState.activePlugin, loader.plugins[0]);
  assert.notEqual(loader.deckyState.activePlugin?.content, stale?.content);
  loader.plugins[0] = { ...loader.plugins[0], version: "0.2.3" };
  assert.equal(
    panel.select(),
    false,
    "do not select a different release if Loader changes during the handoff",
  );
});
