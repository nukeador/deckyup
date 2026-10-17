"""Read public GitHub release pages without spending REST core API quota."""

import json
import logging
import math
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from ._html.parser import HTMLParser

from .tls import github_ssl_context
from .versions import Version

FILTER = "prerelease:false draft:false"
MAX_PAGE = 4 * 1024 * 1024
TTL = 4 * 60 * 60


def _error(message):
    from .github_releases import GitHubError

    return GitHubError(message)


def _trusted(url):
    parsed = urllib.parse.urlsplit(url)
    if (
        parsed.scheme != "https"
        or parsed.netloc not in {"github.com", "raw.githubusercontent.com"}
        or parsed.username
        or parsed.password
    ):
        raise _error("Unexpected GitHub metadata URL")


class MetadataRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        _trusted(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class ReleasePage(HTMLParser):
    def __init__(self, repo):
        super().__init__()
        self.prefix = f"https://github.com/{repo}/releases/expanded_assets/"
        self.filtered = False
        self.tags = []
        self.text = []
        self.section = None
        self.excluded = set()
        self.label = False
        self.prereleases = set()
        self.drafts = set()
        self.next_after = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "a" and (
            attrs.get("rel") == "next" or "next_page" in attrs.get("class", "").split()
        ):
            link = urllib.parse.urlsplit(urllib.parse.urljoin(self.prefix, attrs.get("href", "")))
            expected = urllib.parse.urlsplit(self.prefix)
            query = urllib.parse.parse_qs(link.query)
            if (
                link.scheme == "https"
                and link.netloc == "github.com"
                and link.path == expected.path.split("/expanded_assets/")[0]
            ):
                if len(query.get("after", [])) == 1:
                    self.next_after = query["after"][0]
                elif len(query.get("page", [])) == 1 and re.fullmatch(
                    r"[0-9]{1,5}", query["page"][0]
                ):
                    number = int(query["page"][0])
                    if 2 <= number <= 10000:
                        self.next_after = f"page:{number}"
        if tag == "input" and attrs.get("id") == "release-filter":
            self.filtered = set(FILTER.split()) <= set(attrs.get("value", "").split())
        if tag == "section" and attrs.get("data-release-anchor", "").startswith("release-"):
            self.section = attrs["data-release-anchor"].removeprefix("release-")
        if tag == "span" and "Label" in attrs.get("class", "").split():
            self.label = True
        if tag == "include-fragment" and self.section:
            source = attrs.get("src", "")
            if source.startswith(self.prefix):
                encoded = source[len(self.prefix) :]
                name = urllib.parse.unquote(encoded)
                if name == self.section and name not in self.tags:
                    self.tags.append(name)

    def handle_endtag(self, tag):
        if tag == "section":
            self.section = None
        if tag == "span":
            self.label = False

    def handle_data(self, data):
        if (
            self.label
            and self.section
            and data.strip().lower() in {"pre-release", "prerelease", "draft"}
        ):
            self.excluded.add(self.section)
            if data.strip().lower() == "draft":
                self.drafts.add(self.section)
            else:
                self.prereleases.add(self.section)
        self.text.append(data.strip())

    def versions(self):
        if not self.filtered:
            text = " ".join(self.text).lower().replace("’", "'")
            if "there aren't any releases here" in text:
                return []
            raise _error("GitHub release page format changed; cannot verify stable releases")
        if not self.tags:
            text = " ".join(self.text).lower().replace("’", "'")
            if "there aren't any" not in text and "no releases" not in text:
                raise _error("GitHub release page format changed; cannot read release list")
        versions = []
        for tag in self.tags:
            if tag in self.excluded:
                continue
            try:
                version = Version(tag)
                if not version.pre:
                    versions.append((version, tag))
            except ValueError:
                continue
        return [tag for _, tag in sorted(versions, reverse=True)]


class AssetPage(HTMLParser):
    def __init__(self, repo, tag):
        super().__init__()
        self.prefix = f"/{repo}/releases/download/{urllib.parse.quote(tag, safe='')}/"
        self.assets = []
        self.row = None
        self.depth = 0
        self.has_list = False

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "ul":
            self.has_list = True
        if tag == "li":
            self.depth += 1
            if self.depth == 1:
                self.row = {"links": [], "digests": set()}
        if self.row is None:
            return
        if tag == "a":
            href = attrs.get("href", "")
            if href.startswith(self.prefix):
                filename = urllib.parse.unquote(href[len(self.prefix) :])
                if filename and "/" not in filename and "\\" not in filename:
                    self.row["links"].append((filename, "https://github.com" + href))
        if tag == "clipboard-copy" and re.fullmatch(r"sha256:[a-f0-9]{64}", attrs.get("value", "")):
            self.row["digests"].add(attrs["value"])

    def handle_endtag(self, tag):
        if tag != "li":
            return
        if self.depth == 1 and self.row is not None:
            if len(self.row["links"]) > 1 or len(self.row["digests"]) > 1:
                raise _error("Ambiguous GitHub asset metadata")
            for filename, url in self.row["links"]:
                asset = {
                    "id": filename,
                    "name": filename,
                    "browser_download_url": url,
                    "size": None,
                }
                if self.row["digests"]:
                    asset["digest"] = next(iter(self.row["digests"]))
                self.assets.append(asset)
            self.row = None
        self.depth = max(0, self.depth - 1)


class PublicGitHub:
    def __init__(self, state):
        self.state = state
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPSHandler(context=github_ssl_context()), MetadataRedirect()
        )

    def text(self, url, refresh=False):
        _trusted(url)
        cached = self.state.get("cache", url)
        category = "release metadata" if "/releases" in url else "manifest metadata"
        now = time.time()
        if cached and now - cached["time"] < (60 if refresh else TTL):
            logging.getLogger(__name__).debug("GitHub cache hit: %s", category)
            if cached.get("not_found"):
                raise _error("GitHub repository or manifest not found")
            return cached["data"]
        limit = self.state.get("cache", "_web_rate") or {}
        until = limit.get("until", 0)
        if now < until:
            raise _error(
                f"GitHub temporarily limited web requests; retry in {max(1, math.ceil((until - now) / 60))} min"
            )
        headers = {"User-Agent": "Decky-Direct-Updater/0.1", "Accept-Language": "en-US"}
        if cached and cached.get("etag"):
            headers["If-None-Match"] = cached["etag"]
        logging.getLogger(__name__).debug("GitHub %s request", category)
        try:
            with self.opener.open(
                urllib.request.Request(url, headers=headers), timeout=10
            ) as response:
                _trusted(response.geturl())
                raw = response.read(MAX_PAGE + 1)
                if len(raw) > MAX_PAGE:
                    raise _error("GitHub metadata response is too large")
                data = raw.decode("utf-8")
                self.state.put(
                    "cache",
                    url,
                    {
                        "time": now,
                        "etag": response.headers.get("ETag"),
                        "data": data,
                        "url": response.geturl(),
                    },
                )
                return data
        except urllib.error.HTTPError as error:
            if error.code == 304 and cached:
                self.state.put("cache", url, {**cached, "time": now})
                return cached["data"]
            if error.code == 404:
                self.state.put("cache", url, {"time": now, "data": None, "not_found": True})
                raise _error("GitHub repository or manifest not found") from error
            if error.code in (403, 429):
                try:
                    delay = max(60, float(error.headers.get("Retry-After", 60)))
                except ValueError:
                    delay = 60
                self.state.put("cache", "_web_rate", {"until": now + delay})
                raise _error("GitHub temporarily limited web requests; retry later") from error
            raise _error(f"GitHub web request failed ({error.code})") from error
        except (OSError, UnicodeError) as error:
            raise _error(
                f"Could not read GitHub metadata: {getattr(error, 'reason', error)}"
            ) from error

    def releases(self, repo, refresh=False, plugins=None):
        from .github_releases import compatible_releases

        signature = sorted(
            (
                plugin["name"],
                str(plugin.get("package_name", "")),
            )
            for plugin in plugins or []
        )
        cache_key = "_parsed_releases_v3:" + repo.lower() + ":" + json.dumps(signature)
        cached = self.state.get("cache", cache_key)
        if cached and time.time() - cached["time"] < (60 if refresh else TTL):
            return cached["data"]
        query = urllib.parse.quote(FILTER)
        url = f"https://github.com/{repo}/releases?q={query}"
        content = self.text(url, refresh)
        resolved = (self.state.get("cache", url) or {}).get("url", url)
        parts = urllib.parse.urlsplit(resolved).path.strip("/").split("/")
        if len(parts) == 3 and parts[2] == "releases":
            repo = "/".join(parts[:2])
        page = ReleasePage(repo)
        page.feed(content)
        result = []
        tags = page.versions()[:3]
        if not tags:
            empty = [
                {"id": tag, "tag_name": tag, "draft": False, "prerelease": False, "assets": []}
                for tag in page.tags
                if tag not in page.excluded
            ][:3]
            self.state.put("cache", cache_key, {"time": time.time(), "data": empty})
            return empty
        for tag in tags:
            assets = AssetPage(repo, tag)
            encoded = urllib.parse.quote(tag, safe="")
            assets.feed(self.text(f"https://github.com/{repo}/releases/expanded_assets/{encoded}"))
            if not assets.has_list:
                raise _error("GitHub asset page format changed; cannot verify release assets")
            result.append(
                {
                    "id": tag,
                    "tag_name": tag,
                    "draft": False,
                    "prerelease": False,
                    "assets": assets.assets,
                    "repository": repo,
                }
            )
            if plugins and all(compatible_releases(plugin, result)[0] for plugin in plugins):
                break
        self.state.put("cache", cache_key, {"time": time.time(), "data": result})
        return result

    def release_page(self, repo, after=None, refresh=False):
        # Only server-derived pagination cursors reach this method; never follow a supplied URL.
        if after is not None and (not isinstance(after, str) or not 0 < len(after) <= 512):
            raise ValueError("Invalid release cursor")
        query = {"q": "draft:false"}
        if after:
            if after.startswith("page:"):
                number = after.removeprefix("page:")
                if not number.isdigit() or not 2 <= int(number) <= 10000:
                    raise ValueError("Invalid release page")
                query["page"] = number
            else:
                query["after"] = after
        url = f"https://github.com/{repo}/releases?" + urllib.parse.urlencode(query)
        content = self.text(url, refresh)
        resolved = (self.state.get("cache", url) or {}).get("url", url)
        parts = urllib.parse.urlsplit(resolved).path.strip("/").split("/")
        if len(parts) == 3 and parts[2] == "releases":
            repo = "/".join(parts[:2])
        page = ReleasePage(repo)
        page.feed(content)
        text = " ".join(page.text).lower().replace("’", "'")
        if not page.tags and not any(
            value in text for value in ("there aren't any", "no releases")
        ):
            raise _error("GitHub release page format changed; cannot read release list")
        if len(page.tags) > 10:
            raise _error("Unexpected GitHub release page size")

        def release(tag):
            try:
                Version(tag)
            except ValueError:
                return {
                    "id": tag,
                    "tag_name": tag,
                    "prerelease": tag in page.prereleases,
                    "assets": [],
                    "repository": repo,
                }
            assets = AssetPage(repo, tag)
            encoded = urllib.parse.quote(tag, safe="")
            assets.feed(
                self.text(f"https://github.com/{repo}/releases/expanded_assets/{encoded}", refresh)
            )
            if not assets.has_list:
                raise _error("GitHub asset page format changed; cannot verify release assets")
            return {
                "id": tag,
                "tag_name": tag,
                "prerelease": tag in page.prereleases or bool(Version(tag).pre),
                "assets": assets.assets,
                "repository": repo,
            }

        with ThreadPoolExecutor(max_workers=3) as pool:
            releases = list(pool.map(release, [tag for tag in page.tags if tag not in page.drafts]))
        return {"releases": releases, "next": page.next_after}

    def manifest(self, repo, path, ref="HEAD"):
        encoded = urllib.parse.quote(ref, safe="")
        raw = self.text(f"https://raw.githubusercontent.com/{repo}/{encoded}/{path}")
        if len(raw) > 1024 * 1024:
            raise _error("Oversized GitHub manifest")
        data = json.loads(raw)
        if not isinstance(data, dict):
            raise ValueError("Invalid GitHub manifest")
        return data
