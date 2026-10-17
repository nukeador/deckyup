import assert from "node:assert/strict";
import { test } from "node:test";
import { preferredLocale } from "../site/language.js";

const supported = ["en", "zh", "ru", "es", "pt", "de", "ja", "fr", "pl", "ko"];
test("website language follows saved choice before browser preference order", () => {
  assert.equal(preferredLocale("de", ["es-ES", "en"], supported), "de");
  assert.equal(preferredLocale(null, ["xx", "pt-BR", "es"], supported), "pt");
  assert.equal(preferredLocale("invalid", ["xx", "ko-KR"], supported), "ko");
  assert.equal(preferredLocale(null, ["xx"], supported), "en");
});
test("website recognizes regional and script variants without inventing unsupported languages", () => {
  for (const [tag, expected] of [
    ["ES_mx", "es"],
    ["zh-Hans-CN", "zh"],
    ["pt-PT", "pt"],
    ["ja-JP", "ja"],
    ["EN-us", "en"],
  ]) {
    assert.equal(preferredLocale(null, [tag], supported), expected);
  }
  assert.equal(preferredLocale("en", ["es"], supported), "en");
});
