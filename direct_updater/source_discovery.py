"""Incremental discovery using the existing GitHub client and persistent settings."""

import time

from .installed_plugins import discovery_identity, is_template, repository, source_matches_identity

SEARCH_TTL = 24 * 60 * 60
AUTO_SEARCHES = 2


def candidate(source, description=""):
    return {"repository": source, "owner": source.split("/")[0], "description": description[:160]}


class SourceDiscovery:
    def __init__(self, state, github):
        self.state = state
        self.github = github
        self.remaining_searches = AUTO_SEARCHES

    def cached(self, plugin):
        record = self.state.get("discovery", plugin["id"]) or {}
        if (
            record.get("identity") == discovery_identity(plugin)
            and record.get("fingerprint") == plugin["discovery_fingerprint"]
        ):
            return record
        return {}

    def association(self, plugin):
        record = self.state.get("associations", plugin["id"]) or {}
        if record.get("identity") != discovery_identity(plugin) or record.get("blocked"):
            return None
        if (
            record.get("origin") != "confirmed"
            and record.get("fingerprint") != plugin["discovery_fingerprint"]
        ):
            return None
        return (
            record
            if repository(record.get("source")) and not is_template(record["source"])
            else None
        )

    def save(self, plugin, source, origin):
        self.state.put(
            "associations",
            plugin["id"],
            {
                "identity": discovery_identity(plugin),
                "fingerprint": plugin["discovery_fingerprint"],
                "source": source,
                "origin": origin,
            },
        )

    def remember(self, plugin, **fields):
        record = {
            **self.cached(plugin),
            "identity": discovery_identity(plugin),
            "fingerprint": plugin["discovery_fingerprint"],
            **fields,
        }
        self.state.put("discovery", plugin["id"], record)
        return record

    def decorate(self, plugin, unique=True):
        record = self.association(plugin)
        # Old builds keyed confirmations by display name. Bind only when local
        # project evidence agrees; otherwise retain it as a hint for verification.
        legacy = repository(self.state.get("sources", plugin["name"]))
        if (
            not record
            and not self.state.get("associations", plugin["id"])
            and legacy
            and unique
            and (
                legacy.lower() in {repo.lower() for repo in plugin["source_candidates"]}
                or source_matches_identity(plugin, legacy)
            )
            and not is_template(legacy)
        ):
            self.save(plugin, legacy, "confirmed")
            record = self.association(plugin)
        cached = self.cached(plugin)
        if record:
            plugin.update(source=record["source"], source_note=None)
        elif cached.get("needs_confirmation"):
            plugin.update(source=None, source_note="Choose a GitHub source to continue")
        elif plugin["source"] and not source_matches_identity(plugin, plugin["source"]):
            plugin["source"] = None
        if not plugin["valid_identity"] or not unique:
            plugin["source"] = None
        plugin["suggestions"] = cached.get("suggestions", []) if not plugin["source"] else []
        plugin["discovery_error"] = cached.get("error") if not plugin["source"] else None
        plugin["check_source"] = plugin["source"]
        plugin["status"] = (
            "unchecked"
            if plugin["source"]
            else (
                "source_suggested"
                if plugin["suggestions"]
                else "source_not_found"
                if cached.get("searched") and not cached.get("error")
                else "source_missing"
            )
        )
        return plugin

    def link(self, plugins, lightweight=False):
        if all((self.association(plugin) or {}).get("origin") == "confirmed" for plugin in plugins):
            return
        try:
            database = self.github.official_sources()
        except (ValueError, OSError):
            database = {}
        names = [plugin["name"] for plugin in plugins]
        for plugin in plugins:
            if not plugin["valid_identity"] or names.count(plugin["name"]) != 1:
                continue
            record = self.association(plugin)
            if record and record["origin"] == "confirmed":
                continue
            official = list(
                dict.fromkeys(
                    repo
                    for key in (plugin["id"], plugin.get("package_name", ""))
                    for repo in database.get(key.lower(), [])
                )
            )
            stamp = sorted(repo.lower() for repo in official)
            cached = self.cached(plugin)
            if (
                cached.get("enriched")
                and cached.get("database") == stamp
                and (not cached.get("retry_at") or time.time() < cached["retry_at"])
            ):
                continue
            local = plugin["source_candidates"]
            sources = list({repo.lower(): repo for repo in local + official}.values())
            truncated = len(sources) > 4
            sources = sources[:4]
            if lightweight and not (
                len(sources) == 1
                and plugin["metadata_primary"]
                and source_matches_identity(plugin, sources[0])
            ):
                plugin.update(source=None, check_source=None)
                continue
            error = "Several sources need review; choose a repository" if truncated else None
            verified = []
            try:
                if len(sources) > 1:
                    canonical = [self.github.canonical_repository(repo) for repo in sources]
                    sources = list({repo.lower(): repo for repo in canonical}.values())
                for source in sources:
                    strong = (
                        len(sources) == 1
                        and bool(plugin["metadata_primary"])
                        and source_matches_identity(plugin, source)
                    )
                    if strong or self.github.matches_manifest(source, plugin["name"]):
                        verified.append(candidate(source))
            except (ValueError, OSError) as failure:
                error = str(failure)
            if len(verified) == 1 and not error:
                chosen = verified[0]["repository"]
                self.save(plugin, chosen, "metadata" if local else "official_database")
                self.remember(
                    plugin,
                    enriched=True,
                    database=stamp,
                    suggestions=[],
                    needs_confirmation=False,
                    error=None,
                    retry_at=0,
                )
            else:
                old = self.state.get("associations", plugin["id"])
                if old and old.get("origin") != "confirmed":
                    self.state.put("associations", plugin["id"], {**old, "blocked": True})
                self.remember(
                    plugin,
                    enriched=True,
                    database=stamp,
                    suggestions=verified or cached.get("suggestions", []),
                    needs_confirmation=bool(sources),
                    error=error,
                    retry_at=time.time() + 600 if error else 0,
                )
            # Re-decorate the original local inventory, not a previously resolved source.
            if not self.association(plugin):
                plugin["source"] = None
            self.decorate(plugin)

    def search(self, plugin, force=False):
        cached = self.cached(plugin)
        if not force and time.time() < cached.get("search_time", 0) + SEARCH_TTL:
            return cached.get("suggestions", [])
        hints = list(plugin["source_candidates"])
        legacy = repository(self.state.get("sources", plugin["name"]))
        if legacy and not is_template(legacy):
            hints.append(legacy)
        search_plugin = {
            **plugin,
            "source_candidates": list(
                dict.fromkeys(
                    hints + [item["repository"] for item in cached.get("suggestions", [])]
                )
            ),
        }
        try:
            suggestions = self.github.search(search_plugin)
            self.remember(
                plugin, suggestions=suggestions, searched=True, search_time=time.time(), error=None
            )
            return suggestions
        except (ValueError, OSError) as failure:
            self.remember(plugin, error=str(failure), search_time=time.time() - SEARCH_TTL + 600)
            raise

    def suggest(self, plugins, on_result=None):
        for plugin in plugins:
            if (
                plugin["source"]
                or not plugin["valid_identity"]
                or sum(item["name"] == plugin["name"] for item in plugins) != 1
            ):
                continue
            cached = self.cached(plugin)
            if cached.get("suggestions") or time.time() < max(
                cached.get("retry_at", 0), cached.get("search_time", 0) + SEARCH_TTL
            ):
                continue
            if self.remaining_searches <= 0:
                break
            self.remaining_searches -= 1
            try:
                self.search(plugin)
            except (ValueError, OSError):
                pass
            self.decorate(plugin)
            if on_result:
                on_result(dict(plugin))

    def verify(self, plugin, value):
        source = repository(value)
        if not source or is_template(source):
            raise ValueError(
                "Enter a public GitHub repository as owner/repo or an HTTPS GitHub URL"
            )
        if not self.github.matches_manifest(source, plugin["name"]):
            raise ValueError("This repository does not contain this plugin's Decky manifest")
        suggestions = self.cached(plugin).get("suggestions", [])
        suggestions = [
            item for item in suggestions if item["repository"].lower() != source.lower()
        ] + [candidate(source)]
        self.remember(
            plugin, suggestions=suggestions, searched=True, search_time=time.time(), error=None
        )
        return suggestions

    def confirm(self, plugin, value):
        source = repository(value)
        suggestions = self.cached(plugin).get("suggestions", [])
        if not source or source.lower() not in {item["repository"].lower() for item in suggestions}:
            raise ValueError("Choose a source from this plugin's verified suggestions")
        self.save(plugin, source, "confirmed")
