import assert from "node:assert/strict";
import { test } from "node:test";
import { requestUpdate, type Router } from "../src/deckyInstaller";

const update = {
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
