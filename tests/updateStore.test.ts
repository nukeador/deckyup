import assert from "node:assert/strict";
import { test } from "node:test";
import { CHECK_INTERVAL, createUpdateStore } from "../src/updateStore";
import type { InstalledPlugin } from "../src/uiModel";

const plugin = (status: string, version = "1.0.0"): InstalledPlugin => ({
  id: "example",
  name: "Example",
  version,
  source: "owner/repo",
  status,
});
const tick = () => new Promise<void>((resolve) => setImmediate(resolve));
function fixture() {
  let results = [plugin("update")];
  let failure = false;
  let calls = 0;
  let scheduled = () => {};
  let listener = (_plugin: InstalledPlugin) => {};
  let stopped = 0;
  let release: (() => void) | undefined;
  let gate: Promise<void> | undefined;
  const store = createUpdateStore({
    list: async () => [plugin("unchecked")],
    check: async () => {
      calls++;
      await gate;
      if (failure) throw new Error("Offline");
      return results;
    },
    listen(callback) {
      listener = callback;
      return () => {
        stopped++;
      };
    },
    schedule(callback, milliseconds) {
      assert.equal(milliseconds, CHECK_INTERVAL);
      scheduled = callback;
      return () => {
        stopped++;
      };
    },
  });
  return {
    store,
    results: (next: InstalledPlugin[]) => {
      results = next;
    },
    fail: () => {
      failure = true;
    },
    recover: () => {
      failure = false;
    },
    calls: () => calls,
    timer: () => scheduled(),
    emit: (p: InstalledPlugin) => listener(p),
    stopped: () => stopped,
    block: () => {
      gate = new Promise<void>((resolve) => {
        release = resolve;
      });
    },
    unblock: () => {
      release?.();
      gate = undefined;
    },
  };
}

test("startup and four-hour checks work with the panel closed, and concurrent refreshes coalesce", async () => {
  const f = fixture();
  f.block();
  f.store.start();
  f.store.start();
  const first = f.store.refresh(true);
  const second = f.store.refresh(false);
  assert.equal(first, second);
  await tick();
  assert.equal(f.calls(), 1);
  f.unblock();
  await first;
  assert.equal(f.store.getSnapshot().hasUpdates, true);
  f.results([plugin("current", "1.1.0")]);
  f.timer();
  await tick();
  assert.equal(f.calls(), 2);
  assert.equal(f.store.getSnapshot().hasUpdates, false);
  f.store.dispose();
  assert.equal(f.stopped(), 2);
});

test("failed checks do not invent updates or clear previous positives; valid results clear them", async () => {
  const f = fixture();
  f.results([plugin("error")]);
  f.store.start();
  await tick();
  assert.equal(f.store.getSnapshot().hasUpdates, false);
  f.results([plugin("update")]);
  await f.store.refresh();
  f.results([plugin("error")]);
  await f.store.refresh();
  assert.equal(f.store.getSnapshot().plugins[0].status, "error");
  assert.equal(f.store.getSnapshot().hasUpdates, true);
  f.fail();
  await f.store.refresh();
  assert.equal(f.store.getSnapshot().hasUpdates, true);
  f.recover();
  f.results([plugin("current", "1.1.0")]);
  await f.store.refresh();
  assert.equal(f.store.getSnapshot().hasUpdates, false);
  f.store.dispose();
});

test("progress updates the shared badge without mounting the panel; closed subscriptions and late work are cleaned up", async () => {
  const f = fixture();
  f.results([plugin("current")]);
  f.store.start();
  await tick();
  let notifications = 0;
  const unsubscribe = f.store.subscribe(() => {
    notifications++;
  });
  f.emit(plugin("update"));
  assert.equal(f.store.getSnapshot().hasUpdates, true);
  unsubscribe();
  const count = notifications;
  f.emit(plugin("error"));
  assert.equal(notifications, count);
  assert.equal(f.store.getSnapshot().hasUpdates, true);
  f.block();
  const pending = f.store.refresh();
  f.store.dispose();
  const before = f.store.getSnapshot();
  f.results([plugin("current")]);
  f.unblock();
  await pending;
  f.timer();
  f.emit(plugin("current"));
  assert.equal(f.store.getSnapshot(), before);
  assert.equal(f.stopped(), 2);
});

test("confirmed source identity handles canonical repository redirects and rechecks real installed versions", async () => {
  const f = fixture();
  f.results([
    { ...plugin("update"), source: "new/repo", check_source: "owner/repo" },
  ]);
  f.store.start();
  await tick();
  f.results([{ ...plugin("error"), check_source: "owner/repo" }]);
  await f.store.refresh();
  assert.equal(f.store.getSnapshot().hasUpdates, true);
  f.results([{ ...plugin("error", "1.1.0"), check_source: "owner/repo" }]);
  await f.store.refresh();
  assert.equal(f.store.getSnapshot().hasUpdates, false);
  f.store.dispose();
});

test("reopening rescans local inventory, discovers new plugins and removes uninstalled ones without erasing valid results", async () => {
  let inventory = [plugin("unchecked")];
  let checks = 0;
  let scans = 0;
  const store = createUpdateStore({
    list: async () => {
      scans++;
      return inventory;
    },
    check: async () => {
      checks++;
      return inventory.map((p) => ({
        ...p,
        status: p.source ? "update" : "source_suggested",
      }));
    },
    listen: () => () => {},
    schedule: () => () => {},
  });
  store.start();
  await tick();
  assert.equal(store.getSnapshot().hasUpdates, true);
  inventory = [
    ...inventory,
    {
      ...plugin("source_missing"),
      id: "new",
      source: undefined,
      suggestions: [{ repository: "dev/new" }],
    },
  ];
  await store.refresh(false);
  assert.equal(store.getSnapshot().plugins.length, 2);
  assert.equal(store.getSnapshot().plugins[1].status, "source_suggested");
  inventory = [inventory[1]];
  await store.refresh(false);
  assert.equal(store.getSnapshot().plugins.length, 1);
  assert.equal(store.getSnapshot().hasUpdates, false);
  assert.equal(scans, 3);
  assert.equal(checks, 3);
  store.dispose();
});
