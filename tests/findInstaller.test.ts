import assert from "node:assert/strict";
import { test } from "node:test";
import { createFindInstaller } from "../src/findInstaller";
import type { RepositoryDetails } from "../src/findStore";
const selection: RepositoryDetails = {
  repository: "owner/plugin",
  name: "plugin",
  owner: "owner",
  stars: 1,
  description: "",
  fork: false,
  archived: false,
  disabled: false,
  status: "install",
  token: "opaque",
  release_id: 10,
  asset_id: 20,
};
function setup() {
  const calls = {
    stages: 0,
    requests: 0,
    refresh: 0,
    installed: [] as string[],
    finished: [] as boolean[],
    complete: false,
    reject: false,
  };
  const installer = createFindInstaller({
    async stage(token, release, asset) {
      assert.deepEqual([token, release, asset], ["opaque", 10, 20]);
      calls.stages++;
      return {
        ticket: "ticket",
        artifact: "file:///tmp/staged/update-test.zip",
        name: "plugin",
        version: "1.0.0",
        hash: "a".repeat(64),
        install_type: "install",
      };
    },
    async request() {
      calls.requests++;
      return { requested: !calls.reject };
    },
    async finish(_, cancelled) {
      calls.finished.push(cancelled);
      return { installed: calls.complete && !cancelled };
    },
    async refresh() {
      calls.refresh++;
    },
    installed(repo) {
      calls.installed.push(repo);
    },
  });
  return { calls, installer };
}
test("selecting repository does not install; native prompt request is not completed", async () => {
  const { calls, installer } = setup();
  assert.equal(calls.stages, 0);
  assert.match(await installer.install(selection), /Confirmation requested/);
  assert.deepEqual(calls.installed, []);
  assert.equal(calls.refresh, 0);
  assert.equal(await installer.check(), false);
  assert.equal(calls.refresh, 0);
});
test("completed inventory validation tracks repository and refreshes All once", async () => {
  const { calls, installer } = setup();
  await installer.install(selection);
  calls.complete = true;
  const results = await Promise.all([installer.check(), installer.check()]);
  assert.deepEqual(results, [true, true]);
  assert.deepEqual(calls.installed, [selection.repository]);
  assert.equal(calls.refresh, 1);
  assert.equal(await installer.check(), true);
  assert.equal(calls.refresh, 1);
});
test("cancel and rejected native requests never record a successful install", async () => {
  const { calls, installer } = setup();
  await installer.install(selection);
  await installer.cancel();
  calls.complete = true;
  assert.equal(await installer.check(), false);
  assert.deepEqual(calls.installed, []);
  assert.deepEqual(calls.finished, [true]);
  calls.reject = true;
  await installer.install(selection);
  assert.equal(await installer.check(), false);
  assert.equal(calls.refresh, 0);
});
test("pending native confirmation blocks duplicate preparations", async () => {
  const { calls, installer } = setup();
  await installer.install(selection);
  await installer.install(selection);
  assert.equal(calls.stages, 1);
  assert.equal(calls.requests, 1);
});
test("dispose prevents late completion subscriptions and refresh", async () => {
  const { calls, installer } = setup();
  await installer.install(selection);
  installer.dispose();
  calls.complete = true;
  await installer.check();
  assert.equal(calls.refresh, 0);
  assert.deepEqual(calls.installed, []);
});

test("another plugin's Loader event does not confirm a pending installation", async () => {
  const { calls, installer } = setup();
  await installer.install(selection);
  calls.complete = true;
  assert.equal(await installer.check("unrelated"), false);
  assert.deepEqual(calls.finished, []);
  assert.equal(await installer.check("plugin"), true);
});
