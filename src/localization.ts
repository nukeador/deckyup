import en from "./locales/en.json";
import es from "./locales/es.json";
import de from "./locales/de.json";
import fr from "./locales/fr.json";
import ja from "./locales/ja.json";
import ko from "./locales/ko.json";
import pl from "./locales/pl.json";
import pt from "./locales/pt.json";
import ru from "./locales/ru.json";
import zh from "./locales/zh.json";

const translations: Record<string, Record<string, string>> = {
  en,
  es,
  de,
  fr,
  ja,
  ko,
  pl,
  pt,
  ru,
  zh,
};
const steamLanguages: Record<string, string> = {
  english: "en",
  spanish: "es",
  german: "de",
  french: "fr",
  japanese: "ja",
  koreana: "ko",
  korean: "ko",
  polish: "pl",
  portuguese: "pt",
  brazilian: "pt",
  russian: "ru",
  schinese: "zh",
  tchinese: "zh",
  chinese: "zh",
};
export function resolveLanguage(value: string): string {
  const normalized = value.trim().toLowerCase().replace(/_/g, "-");
  const candidate = steamLanguages[normalized] || normalized.split("-")[0];
  return candidate in translations ? candidate : "en";
}
export function translate(language: string, key: string): string {
  return translations[language]?.[key] || en[key as keyof typeof en] || key;
}
