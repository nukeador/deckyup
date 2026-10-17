import assert from "node:assert/strict";
import { test } from "node:test";
import {
  emptyMessage,
  initialNavigation,
  navigate,
  pluginActions,
  pluginStatus,
  restoreBookmark,
  visiblePlugins,
  type InstalledPlugin,
} from "../src/uiModel";

const plugin = (id: string, status: string, name = id): InstalledPlugin => ({
  id,
  name,
  status,
  version: "1.0.0",
  latest: "1.1.0",
  source: status === "source_missing" ? undefined : "owner/repo",
  release_id: "v1.1.0",
  asset_id: "plugin.zip",
});

test("Updates includes confirmed updates and unresolved sources; All includes every plugin with updates first", () => {
  const plugins = [
    plugin("z", "current"),
    plugin("b", "source_missing"),
    plugin("c", "update"),
    plugin("a", "update"),
    plugin("d", "error"),
    plugin("e", "unchecked"),
  ];
  assert.deepEqual(
    visiblePlugins(plugins, "updates").map((p) => p.id),
    ["a", "c", "b"],
  );
  assert.deepEqual(
    visiblePlugins(plugins, "all").map((p) => p.id),
    ["a", "c", "b", "d", "e", "z"],
  );
  assert.equal(plugins[0].id, "z");
});

test("all states have a concise label and the appropriate status icon", () => {
  for (const [status, icon, label] of [
    ["update", "download", "Update available"],
    ["current", "check", "Up to date"],
    ["source_missing", "question", "Source unknown"],
    ["source_suggested", "question", "Source suggested"],
    ["source_not_found", "question", "Source not found"],
    ["error", "warning", "Check failed"],
    ["unchecked", "clock", "Not checked"],
    ["no_release", "unavailable", "No stable GitHub release"],
    ["no_compatible_release", "unavailable", "No compatible release"],
    ["ambiguous", "warning", "Ambiguous release"],
    ["version_unavailable", "warning", "Version unavailable"],
  ]) {
    const result = pluginStatus(plugin("test", status));
    assert.equal(result.icon, icon);
    assert.equal(result.label, label);
    assert.ok(
      result.subtitle.includes(status === "update" ? "1.0.0 → 1.1.0" : label),
    );
  }
  assert.equal(pluginStatus(plugin("test", "unexpected")).label, "Not checked");
});

test("only actionable confirmed updates offer Update; source and Retry actions follow state", () => {
  assert.equal(pluginActions(plugin("test", "update")).update, true);
  for (const status of [
    "current",
    "unchecked",
    "error",
    "source_missing",
    "ambiguous",
    "no_release",
  ]) {
    assert.equal(pluginActions(plugin("test", status)).update, false);
  }
  assert.equal(
    pluginActions({ ...plugin("test", "update"), asset_id: undefined }).update,
    false,
  );
  assert.equal(
    pluginActions(plugin("test", "source_missing")).findSource,
    true,
  );
  assert.equal(pluginActions(plugin("test", "current")).changeSource, true);
  assert.equal(pluginActions(plugin("test", "error")).retry, true);
  assert.equal(pluginActions(plugin("test", "unchecked")).retry, true);
  assert.equal(pluginActions(plugin("test", "current")).retry, false);
});

test("selecting a row opens only details; Back restores the original view and bookmark", () => {
  const opened = navigate(initialNavigation, {
    type: "open",
    id: "mako",
    scrollTop: 240,
  });
  assert.equal(opened.detailId, "mako");
  assert.deepEqual(opened.bookmarks.updates, {
    selectedId: "mako",
    scrollTop: 240,
  });
  const back = navigate(opened, { type: "back" });
  assert.equal(back.detailId, null);
  assert.equal(back.view, "updates");
  assert.deepEqual(back.bookmarks.updates, opened.bookmarks.updates);
  assert.deepEqual(initialNavigation.bookmarks.updates, {
    selectedId: null,
    scrollTop: 0,
  });
});

test("each view remembers its own selection and scroll independently", () => {
  let state = navigate(initialNavigation, {
    type: "open",
    id: "update-2",
    scrollTop: 110,
  });
  state = navigate(state, { type: "back" });
  state = navigate(state, { type: "view", view: "all", scrollTop: 110 });
  state = navigate(state, { type: "focus", id: "plugin-20" });
  state = navigate(state, { type: "view", view: "updates", scrollTop: 980 });
  assert.deepEqual(state.bookmarks.all, {
    selectedId: "plugin-20",
    scrollTop: 980,
  });
  assert.deepEqual(state.bookmarks.updates, {
    selectedId: "update-2",
    scrollTop: 110,
  });
});

test("restoring focus prevents browser scrolling before restoring the list offset", () => {
  const calls: unknown[] = [];
  const container = { scrollTop: 0 };
  const target = {
    focus: (options?: FocusOptions) => {
      calls.push(options);
      container.scrollTop = 999;
    },
  };
  restoreBookmark(container, target, { selectedId: "plugin", scrollTop: 175 });
  assert.deepEqual(calls, [{ preventScroll: true }]);
  assert.equal(container.scrollTop, 175);
  restoreBookmark(container, undefined, { selectedId: null, scrollTop: 32 });
  assert.equal(container.scrollTop, 32);
});

test("loading, unresolved sources and failed checks never claim everything is up to date", () => {
  assert.match(emptyMessage([plugin("x", "current")], true, false), /Checking/);
  assert.match(
    emptyMessage([plugin("x", "current")], false, true),
    /Could not check/,
  );
  for (const status of ["error", "unchecked", "source_missing", "no_release"]) {
    assert.doesNotMatch(
      emptyMessage([plugin("x", status)], false, false),
      /Everything is up to date/,
    );
  }
  assert.equal(
    emptyMessage([plugin("x", "current")], false, false),
    "Everything is up to date.",
  );
  assert.equal(emptyMessage([], false, false), "No installed plugins found.");
});

test("returned refresh results update rows without changing the navigation bookmark", () => {
  const navigation = navigate(initialNavigation, {
    type: "open",
    id: "same",
    scrollTop: 56,
  });
  const before = [plugin("same", "update")];
  const after = [{ ...before[0], version: "1.1.0", status: "current" }];
  assert.equal(visiblePlugins(after, "updates").length, 0);
  assert.equal(visiblePlugins(after, "all")[0].id, before[0].id);
  assert.equal(navigation.bookmarks.updates.scrollTop, 56);
});

test("unresolved sources appear on the main screen with a question icon and source actions, never Update", () => {
  for (const status of [
    "source_missing",
    "source_suggested",
    "source_not_found",
  ]) {
    const unresolved = { ...plugin("review", status), source: undefined };
    assert.equal(visiblePlugins([unresolved], "updates")[0], unresolved);
    assert.equal(pluginStatus(unresolved).icon, "question");
    assert.equal(pluginActions(unresolved).findSource, true);
    assert.equal(pluginActions(unresolved).update, false);
  }
  assert.equal(
    visiblePlugins([plugin("known", "current")], "updates").length,
    0,
  );
});
