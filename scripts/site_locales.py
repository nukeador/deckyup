"""Render complete static translations; no runtime framework or translation requests."""

import html
import json
import re
from pathlib import Path

BASE = "https://deckyup.nukeador.com/"
# Steam's September 2026 combined-platform language survey (see docs/website.md).
LOCALES = {
    "en": ("en", "English"),
    "zh": ("zh-Hans", "简体中文"),
    "ru": ("ru", "Русский"),
    "es": ("es", "Español"),
    "pt": ("pt", "Português"),
    "de": ("de", "Deutsch"),
    "ja": ("ja", "日本語"),
    "fr": ("fr", "Français"),
    "pl": ("pl", "Polski"),
    "ko": ("ko", "한국어"),
}


def dictionaries(source):
    result = {
        code: json.loads((source / "locales" / (code + ".json")).read_text()) for code in LOCALES
    }
    keys = set(result["en"])
    for code, entries in result.items():
        if set(entries) != keys or any(
            not isinstance(v, str) or not v.strip() for v in entries.values()
        ):
            raise ValueError(f"Incomplete website translation: {code}")
    return result


def render_pages(source, output):
    source, output = Path(source), Path(output)
    template = (source / "index.html").read_text()
    strings = dictionaries(source)
    for route in ("", *LOCALES):
        code = route or "en"
        prefix = "../" if route else "./"
        path = output / route
        path.mkdir(parents=True, exist_ok=True)
        canonical = BASE + (code + "/" if code != "en" else "")
        context = {key: html.escape(value, quote=True) for key, value in strings[code].items()}
        context.update(
            lang=LOCALES[code][0],
            default_entry="false" if route else "true",
            prefix=prefix,
            canonical=canonical,
        )
        context["alternates"] = (
            "\n".join(
                f'<link rel="alternate" hreflang="{tag}" href="{BASE + (locale + "/" if locale != "en" else "")}" />'
                for locale, (tag, _) in LOCALES.items()
            )
            + f'\n<link rel="alternate" hreflang="x-default" href="{BASE}" />'
        )
        # /en/ makes an explicit English choice work even when storage is blocked.
        context["language_options"] = "\n".join(
            f'<option value="{locale}" lang="{LOCALES[locale][0]}" data-url="{prefix}{locale}/"'
            + (" selected" if locale == code else "")
            + f">{name}</option>"
            for locale, (_, name) in LOCALES.items()
        )
        context["language_links"] = " ".join(
            f'<a href="{prefix}{locale}/" lang="{tag}" hreflang="{tag}">{name}</a>'
            for locale, (tag, name) in LOCALES.items()
        )
        separator = "" if code in {"zh", "ja"} else " "
        context["zip_alternative"] = (
            context["zip_before"]
            + separator
            + f'<a href="{prefix}install.zip" download>{context["zip_download"]}</a>'
            + separator
            + context["zip_after"]
        )

        def replace(match):
            if match[1] not in context:
                raise ValueError(f"Unknown website translation key: {match[1]}")
            return context[match[1]]

        page = re.sub(r"\{\{([a-z0-9_]+)\}\}", replace, template)
        if "{{" in page:
            raise ValueError("Unresolved website translation placeholder")
        (path / "index.html").write_text(page, encoding="utf-8")
