"""Bounded unauthenticated GitHub REST access and conservative asset selection."""

import json
import logging
import math
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

from .installed_plugins import is_template, repository
from .versions import Version
from .tls import github_ssl_context

CACHE_SECONDS = 4 * 60 * 60
MAX_JSON = 4 * 1024 * 1024


class GitHubError(ValueError):
    pass


class SafeRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        check_download_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def check_download_url(url):
    parsed = urllib.parse.urlsplit(url)
    if (
        parsed.scheme != "https"
        or parsed.username
        or parsed.password
        or parsed.port not in (None, 443)
        or parsed.hostname
        not in {
            "github.com",
            "release-assets.githubusercontent.com",
            "objects.githubusercontent.com",
            "api.github.com",
        }
    ):
        raise ValueError("Release URL is not a trusted GitHub HTTPS location")


class GitHub:
    def __init__(self, state):
        self.state = state
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPSHandler(context=github_ssl_context()), SafeRedirect()
        )
        self.lock = threading.RLock()
        self.limits = {}
        for resource in ("core", "search"):
            saved = self.state.get("cache", "_rate_" + resource)
            if isinstance(saved, dict):
                self.limits[resource] = saved.get("until", 0)

    def get(self, endpoint, refresh=False):
        if not endpoint.startswith("/") or endpoint.startswith("//"):
            raise ValueError("Invalid GitHub API endpoint")
        # Serialize cache fills so shared repositories only generate one request.
        with self.lock:
            cached = self.state.get("cache", endpoint)
            now = time.time()
            if cached and now - cached["time"] < (60 if refresh else CACHE_SECONDS):
                if cached.get("not_found"):
                    raise GitHubError("GitHub repository or manifest not found")
                return cached["data"]
            resource = "search" if endpoint.startswith("/search/") else "core"
            if now < self.limits.get(resource, 0):
                raise self._limit_error(resource)
            headers = {
                "User-Agent": "Decky-Direct-Updater/0.1",
                "Accept": "application/vnd.github+json",
            }
            if cached and cached.get("etag"):
                headers["If-None-Match"] = cached["etag"]
            request = urllib.request.Request("https://api.github.com" + endpoint, headers=headers)
            try:
                with self.opener.open(request, timeout=25) as response:
                    self._rate_headers(response.headers, resource)
                    raw = response.read(MAX_JSON + 1)
                    if len(raw) > MAX_JSON:
                        raise GitHubError("GitHub response is too large")
                    data = json.loads(raw)
                    self.state.put(
                        "cache",
                        endpoint,
                        {
                            "time": now,
                            "etag": response.headers.get("ETag"),
                            "data": data,
                        },
                    )
                    return data
            except urllib.error.HTTPError as error:
                self._rate_headers(error.headers, resource)
                if error.code == 304 and cached:
                    self.state.put("cache", endpoint, {**cached, "time": now})
                    return cached["data"]
                if error.code in (403, 429):
                    body = error.read(4096).decode("utf-8", errors="replace") if error.fp else ""
                    limited = (
                        error.code == 429
                        or error.headers.get("X-RateLimit-Remaining") == "0"
                        or error.headers.get("Retry-After")
                        or "rate limit" in body.lower()
                    )
                    if limited:
                        self._set_limit(resource, max(self.limits.get(resource, 0), now + 60))
                        raise self._limit_error(resource) from error
                    raise GitHubError(
                        "GitHub denied this request (403); repository access unavailable"
                    ) from error
                if error.code == 404:
                    self.state.put(
                        "cache", endpoint, {"time": now, "data": None, "not_found": True}
                    )
                    raise GitHubError("GitHub repository or manifest not found") from error
                raise GitHubError(f"GitHub API error ({error.code})") from error
            except GitHubError:
                raise
            except (OSError, ValueError) as error:
                reason = getattr(error, "reason", error)
                logging.getLogger(__name__).warning("GitHub request failed: %s", reason)
                if "CERTIFICATE_VERIFY_FAILED" in str(reason):
                    message = "Could not verify GitHub TLS certificate; check system clock and CA certificates"
                else:
                    message = "Could not check GitHub; check connection and retry"
                raise GitHubError(message) from error

    def _set_limit(self, resource, until):
        self.limits[resource] = until
        self.state.put("cache", "_rate_" + resource, {"until": until})

    def _limit_error(self, resource):
        minutes = max(1, math.ceil((self.limits.get(resource, 0) - time.time()) / 60))
        return GitHubError(
            f"GitHub rate limit reached; retry in {minutes} min. Cached results remain available."
        )

    def _rate_headers(self, headers, resource):
        try:
            if headers.get("X-RateLimit-Remaining") == "0":
                self._set_limit(
                    resource,
                    max(self.limits.get(resource, 0), float(headers.get("X-RateLimit-Reset", 0))),
                )
            if headers.get("Retry-After"):
                until = time.time() + float(headers["Retry-After"])
                for bucket in ("core", "search"):
                    self._set_limit(bucket, max(self.limits.get(bucket, 0), until))
        except ValueError:
            pass

    def releases(self, repo, refresh=False, plugins=None):
        from .github_web import PublicGitHub

        return PublicGitHub(self.state).releases(repo, refresh, plugins)

    def release_page(self, repo, after=None, refresh=False):
        from .github_web import PublicGitHub

        return PublicGitHub(self.state).release_page(repo, after, refresh)

    def official_sources(self):
        from .github_web import PublicGitHub
        from .official_database import URL, TTL, parse_gitmodules

        key = "_official_database_v1"
        cached = self.state.get("cache", key) or {}
        now = time.time()
        if now < cached.get("retry_at", 0) or now - cached.get("time", 0) < TTL:
            return cached.get("data", {})
        try:
            data = parse_gitmodules(PublicGitHub(self.state).text(URL))
            self.state.put("cache", key, {"time": now, "data": data})
            return data
        except (ValueError, OSError):
            self.state.put("cache", key, {**cached, "retry_at": now + 600})
            return cached.get("data", {})

    def canonical_repository(self, source):
        from .github_web import FILTER, PublicGitHub

        url = f"https://github.com/{source}/releases?q=" + urllib.parse.quote(FILTER)
        PublicGitHub(self.state).text(url)
        resolved = (self.state.get("cache", url) or {}).get("url", url)
        return (
            repository(
                urllib.parse.urlsplit(resolved)
                ._replace(query="", fragment="")
                .geturl()
                .removesuffix("/releases")
            )
            or source
        )

    def search(self, plugin):
        candidates = []
        seen = set()

        def ranked():
            # At most two credible matches get a release hint. Use the same public
            # metadata cache; missing releases never invalidate a matching manifest.
            for item in candidates[:2]:
                try:
                    choices, ambiguous = compatible_releases(
                        plugin, self.releases(item["repository"], plugins=[plugin])
                    )
                    item["compatible_release"] = bool(choices) and not ambiguous
                except (ValueError, OSError):
                    item["compatible_release"] = None
            return sorted(
                candidates, key=lambda item: item.get("compatible_release") is True, reverse=True
            )

        def consider(repo, description=""):
            repo = repository(repo)
            if repo and not is_template(repo) and repo.lower() not in seen:
                seen.add(repo.lower())
                if self.matches_manifest(repo, plugin["name"]):
                    candidates.append(
                        {
                            "repository": repo,
                            "owner": repo.split("/")[0],
                            "description": str(description or "")[:160],
                        }
                    )

        for repo in plugin.get("source_candidates", []):
            consider(repo)
        if candidates:
            return ranked()
        package = plugin.get("package_name", "")
        terms = []
        author = plugin.get("author", "")
        if isinstance(author, dict):
            author = author.get("name", "")
        keywords = [
            word
            for word in re.findall(r"[A-Za-z0-9]+", package or plugin["name"])
            if word.lower() not in {"decky", "plugin", "template", "manager"}
        ]
        if (
            isinstance(author, str)
            and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9-]{0,38}", author)
            and keywords
        ):
            terms.append(" ".join(keywords[:2]) + " user:" + author + " in:name,description")
        if package and "template" not in package.lower():
            terms.append(package + " in:name")
        terms.append(plugin["name"] + " in:name,description")
        for term in terms[:2]:
            query = urllib.parse.quote(term)
            response = self.get("/search/repositories?q=" + query + "&per_page=4")
            if not isinstance(response, dict) or not isinstance(response.get("items"), list):
                raise GitHubError("Unexpected GitHub search response; retry later")
            for item in response["items"]:
                if isinstance(item, dict):
                    consider(item.get("full_name", ""), item.get("description"))
            if candidates:
                break
        return ranked()

    def matches_manifest(self, repo, name):
        from .github_web import PublicGitHub

        repo = repository(repo)
        if not repo or is_template(repo):
            return False
        public = PublicGitHub(self.state)
        for path in ("plugin.json", "plugin/plugin.json"):
            try:
                if public.manifest(repo, path).get("name") == name:
                    return True
            except GitHubError as error:
                if "not found" not in str(error):
                    raise
            except (ValueError, KeyError, TypeError):
                continue
        return False


def _identity(value):
    words = re.findall(r"[a-z0-9]+", str(value).lower())
    return "".join(word for word in words if word not in {"plugin", "decky"})


def _matches_asset(plugin, filename, tag):
    if not filename.lower().endswith(".zip"):
        return False
    stem = re.sub(r"(?:[-_]?v)?\d+\.\d+\.\d+.*$", "", filename[:-4], flags=re.I)
    words = set(re.findall(r"[a-z0-9]+", stem.lower()))
    if words & {"source", "src", "sources", "sourcecode", "master", "main"}:
        return False
    identities = {_identity(plugin["name"]), _identity(plugin.get("package_name", ""))} - {""}
    asset_identity = _identity(stem)
    if not any(len(identity) >= 3 and asset_identity == identity for identity in identities):
        return False
    # Divergent package/display names can indicate a multi-component repository.
    # Require an explicit Decky/plugin marker rather than selecting a sibling app.
    if (
        len(identities) > 1
        and asset_identity != _identity(plugin["name"])
        and not (words & {"decky", "plugin"} or tag.lower().startswith("plugin-"))
    ):
        return False
    return True


def compatible_releases(plugin, releases, allow_prerelease=False):
    compatible = []
    ambiguous = []
    for release in releases:
        if release.get("draft") or (release.get("prerelease") and not allow_prerelease):
            continue
        try:
            version = Version(release.get("tag_name", ""))
        except ValueError:
            continue
        if version.pre and not allow_prerelease:
            continue
        assets = []
        for asset in release.get("assets", []):
            name = asset.get("name", "")
            if not _matches_asset(plugin, name, release.get("tag_name", "")):
                continue
            # Asset versions, when supplied, must agree with the release tag.
            embedded = re.findall(r"\d+\.\d+\.\d+(?:-[0-9A-Za-z.]+)?", name.removesuffix(".zip"))
            try:
                if embedded and any(Version(value) != version for value in embedded):
                    continue
            except ValueError:
                continue
            assets.append(asset)
        if len(assets) == 1:
            compatible.append((version, release, assets[0]))
        elif assets:
            ambiguous.append(version)
    compatible.sort(key=lambda item: item[0], reverse=True)
    if len(compatible) > 1 and compatible[0][0] == compatible[1][0]:
        return [], True
    if ambiguous and (not compatible or max(ambiguous) >= compatible[0][0]):
        return [], True
    return compatible, False
