import assert from "node:assert/strict";
import { test } from "node:test";
import { resolveLanguage, translate } from "../src/localization";
import en from "../src/locales/en.json";
import es from "../src/locales/es.json";
import de from "../src/locales/de.json";
import fr from "../src/locales/fr.json";
import ja from "../src/locales/ja.json";
import ko from "../src/locales/ko.json";
import pl from "../src/locales/pl.json";
import pt from "../src/locales/pt.json";
import ru from "../src/locales/ru.json";
import zh from "../src/locales/zh.json";

const locales = { en, es, de, fr, ja, ko, pl, pt, ru, zh };

test("all ten locales contain complete non-empty translations", () => {
  for (const [locale, dictionary] of Object.entries(locales)) {
    assert.deepEqual(
      Object.keys(dictionary).sort(),
      Object.keys(en).sort(),
      locale,
    );
    for (const [key, value] of Object.entries(dictionary)) {
      assert.ok(value.trim(), `${locale}: ${key}`);
    }
  }
});

test("Decky follows Steam language identifiers and common regional variants", () => {
  for (const [setting, locale] of Object.entries({
    english: "en",
    spanish: "es",
    german: "de",
    french: "fr",
    japanese: "ja",
    koreana: "ko",
    polish: "pl",
    portuguese: "pt",
    brazilian: "pt",
    russian: "ru",
    schinese: "zh",
    tchinese: "zh",
    "es-ES": "es",
    "pt-BR": "pt",
    "zh-CN": "zh",
  })) {
    assert.equal(resolveLanguage(setting), locale, setting);
  }
  assert.equal(resolveLanguage("unsupported"), "en");
  assert.equal(translate("es", "You're up to date"), "Todo actualizado");
  assert.equal(translate("es", "Up to date"), "Actualizado");
  assert.equal(translate("es", "nonexistent key"), "nonexistent key");
});

test("compact Spanish security review uses the agreed decision copy", () => {
  assert.equal(
    es["This plugin requests administrator access"],
    "Este plugin solicita acceso de administrador",
  );
  assert.equal(
    es[
      "It can modify SteamOS files and settings. Install it only if you trust its developer."
    ],
    "Podrá modificar archivos y ajustes de SteamOS. Instálalo solo si confías en su desarrollador.",
  );
  assert.equal(
    es["I understand it will have administrator access."],
    "Entiendo que tendrá acceso de administrador.",
  );
  assert.equal(es.Continue, "Continuar");
});
