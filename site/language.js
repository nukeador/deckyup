export function preferredLocale(saved, browserLanguages, supported) {
  const normalize = (tag) =>
    String(tag || "")
      .trim()
      .toLowerCase()
      .split(/[-_]/)[0];
  const savedLocale = normalize(saved);
  if (supported.includes(savedLocale)) return savedLocale;
  return (
    browserLanguages.map(normalize).find((code) => supported.includes(code)) ||
    "en"
  );
}
