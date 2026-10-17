import assert from "node:assert/strict";
import { test } from "node:test";
import {
  createFindStore,
  formatStars,
  type Repository,
  type SearchPage,
} from "../src/findStore";

const row = (index = 0): Repository => ({
  repository: `owner/Plugin${index}`,
  name: `Plugin${index}`,
  owner: "owner",
  stars: 1200,
  description: "Decky plugin",
  fork: index === 1,
  archived: false,
  disabled: false,
});
const deferred = <T>() => {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((done) => {
    resolve = done;
  });
  return { promise, resolve };
};
test("opening, typing, back and cached resubmit add zero requests; one submit fetches 25 rows", async () => {
  let calls = 0;
  const store = createFindStore(async () => {
    calls++;
    return {
      results: Array.from({ length: 25 }, (_, i) => row(i)),
      next_page: 2,
    };
  });
  assert.equal(calls, 0);
  store.type("MAKO");
  assert.equal(calls, 0);
  await store.submit();
  assert.equal(calls, 1);
  assert.equal(store.getSnapshot().visible, 5);
  for (let i = 0; i < 4; i++) await store.more();
  assert.equal(store.getSnapshot().visible, 25);
  assert.equal(calls, 1);
  assert.equal(store.getSnapshot().results[1].fork, true);
  // Navigating leaves this plugin-lifetime store intact.
  assert.equal(store.getSnapshot().query, "MAKO");
  await store.submit();
  assert.equal(calls, 1);
});
test("only explicit Show more after fetched rows are exhausted requests page two", async () => {
  const calls: number[] = [];
  const store = createFindStore(async (_, page) => {
    calls.push(page);
    return {
      results: Array.from({ length: 25 }, (_, i) => row(i + (page - 1) * 25)),
      next_page: page === 1 ? 2 : null,
    };
  });
  store.type("MAKO");
  await store.submit();
  for (let i = 0; i < 4; i++) await store.more();
  assert.deepEqual(calls, [1]);
  await store.more();
  assert.deepEqual(calls, [1, 2]);
  assert.equal(store.getSnapshot().results.length, 50);
  assert.equal(store.getSnapshot().visible, 30);
});
test("identical concurrent submissions share one RPC", async () => {
  let calls = 0;
  const request = deferred<SearchPage>();
  const store = createFindStore(() => {
    calls++;
    return request.promise;
  });
  store.type("MAKO");
  const first = store.submit();
  const second = store.submit();
  assert.equal(calls, 1);
  request.resolve({ results: [row()] });
  await Promise.all([first, second]);
  assert.equal(store.getSnapshot().results.length, 1);
});
test("older query and old pagination responses cannot replace newer results", async () => {
  const slow = deferred<SearchPage>();
  const store = createFindStore((query) =>
    query === "old" ? slow.promise : Promise.resolve({ results: [row(2)] }),
  );
  store.type("old");
  const old = store.submit();
  store.type("new");
  await store.submit();
  slow.resolve({ results: [row(1)] });
  await old;
  assert.equal(store.getSnapshot().results[0].name, "Plugin2");
  assert.equal(store.getSnapshot().submitted, "new");
});
test("direct result opens details once and clearing it makes no requests", async () => {
  let calls = 0;
  const store = createFindStore(async () => {
    calls++;
    return { results: [row()], direct: true };
  });
  store.type("owner/Plugin0");
  await store.submit();
  assert.equal(store.getSnapshot().direct?.name, "Plugin0");
  store.clearDirect();
  assert.equal(store.getSnapshot().direct, null);
  assert.equal(calls, 1);
});
test("search failures preserve cached rows without automatic retries", async () => {
  let calls = 0;
  const store = createFindStore(async () => {
    calls++;
    return calls === 1
      ? { results: [row()] }
      : { error: "GitHub search limit reached.", results: [row()] };
  });
  store.type("first");
  await store.submit();
  store.type("second");
  await store.submit();
  assert.match(store.getSnapshot().error, /limit/);
  assert.equal(store.getSnapshot().results.length, 1);
  assert.equal(calls, 2);
  store.type("first");
  await store.submit();
  assert.equal(calls, 2);
});
test("disposed store drops responses and removes subscriptions", async () => {
  const request = deferred<SearchPage>();
  let notifications = 0;
  const store = createFindStore(() => request.promise);
  store.subscribe(() => notifications++);
  store.type("MAKO");
  const run = store.submit();
  store.dispose();
  const before = notifications;
  request.resolve({ results: [row()] });
  await run;
  assert.equal(notifications, before);
  assert.equal(store.getSnapshot().results.length, 0);
});
test("star formatting preserves compact familiar counts", () => {
  assert.deepEqual([840, 1200, 15000, 999999].map(formatStars), [
    "840",
    "1.2k",
    "15k",
    "1000k",
  ]);
});
