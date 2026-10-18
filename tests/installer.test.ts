import assert from "node:assert/strict";
import { test } from "node:test";
import {
  requestUpdate,
  requestSelfUpdate,
  reopenAfterSelfUpdate,
  type Router,
} from "../src/deckyInstaller";

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
    );
    assert.equal(closed, 0);
    await reopenAfterSelfUpdate(
      async () => [{ name: self.name, version: self.version }],
      navigation,
    );
    assert.equal(closed, 1);
    await reopenAfterSelfUpdate(
      async () => [{ name: self.name, version: self.version }],
      navigation,
    );
    assert.equal(closed, 1);
    await requestSelfUpdate(self, async () => ({ requested: false }));
    await reopenAfterSelfUpdate(
      async () => [{ name: self.name, version: self.version }],
      navigation,
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
