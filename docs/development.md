# Development and implementation details

Keep your Decky plugins up to date directly from their developers.

Decky Direct Updater checks the public GitHub releases of **already installed** plugins from Gaming Mode. It is an optional alternative for following developers' release schedules alongside the curated official Decky Store. This independent community project is not affiliated with the Decky Loader team.

## Features

- List installed plugins, including disabled plugins, with versions from package metadata.
- Identify GitHub repositories from installed metadata and persist user-confirmed sources.
- Find unresolved sources with on-demand GitHub repository search and exact Decky manifest matching, including nested `plugin/plugin.json`.
- Check newer stable releases automatically; compare SemVer and reject ambiguous ZIP assets.
- Browse paginated releases and manually select prereleases or explicitly confirmed downgrades.
- Show a green update indicator on the Decky icon, with shared checks at load and every four hours.
- Download, hash, and validate packages before requesting Decky's native update confirmation.
- Update this plugin through the same pipeline as every other installed plugin.

## How it works

Local installed metadata → confirmed GitHub repository → stable release and matching ZIP → local download → identity, version, integrity and path validation → Decky installation request → native confirmation.

Release checks read GitHub’s public release pages using its stable-release filter and official asset links, rather than spending the unauthenticated REST core quota. Source search alone uses the repository search API; candidate manifests come from raw.githubusercontent.com. The Python backend performs blocking work in worker threads. The React QAM panel uses standard Decky controls. A small frontend adapter isolates the internal Loader installer route; the current public `@decky/api` has no installed-plugin inventory or installer API. Inventory comes from the parent of Decky's runtime `DECKY_PLUGIN_DIR`, without modifying installed files or requesting root.

## Installation

The first milestone is local hardware testing. Build an installable ZIP using the instructions below, transfer it to the Deck, and choose **Install Plugin from ZIP** in Decky Settings with Developer Mode enabled. See the [Steam Deck testing guide](steam-deck-testing.md) for exact steps, controlled fixture upgrades, cancellation, logs, and recovery. No GitHub release is needed.

## Updating plugins

Open Decky Direct Updater in QAM. Local plugins load first; identified sources are checked using a four-hour persistent cache. **Check for updates** revalidates results, with a one-minute minimum interval to prevent repeated button presses from sending duplicate requests. GitHub results use ETags, timeouts, bounded requests, negative caching and persistent rate-limit backoff. Repository search still has its own GitHub search limit; the public website can also throttle requests. These are reported separately from release-check failures. Offline and failed checks have explicit error states.

The compact **Updates** view shows confirmed updates and unresolved sources marked with a question icon; **All** includes every installed plugin, with updates first. Select a two-line row to open its details. Source selection, retry and **Change source** actions live there. The refresh icon keeps the list visible while checking. Back returns to the previous selection and scroll position.

Choose **Update** in the detail view to stage a release and request Decky's native prompt. Accept or cancel there. A requested prompt is never reported as a completed installation. Check again after installation to read the actual installed version.

## Source identification

Opening the panel immediately reloads installed plugins and saved associations, then asynchronously discovers sources and checks releases. Existing results stay visible while cached checks run. New and removed plugins are picked up on subsequent openings; no setup button is required.

Discovery reuses the existing GitHub client, cache and backoff. It reads repository/homepage/bugs hints from both `package.json` and `plugin.json`, filters templates and normalizes GitHub HTTPS, shorthand, git and SSH references. Explicit metadata with an exact local project identifier can be linked immediately; weaker hints are checked against the exact root or nested Decky manifest name.

The official [Decky plugin database](https://github.com/SteamDeckHomebrew/decky-plugin-database) supplies additional repository hints through its `.gitmodules` file. Only that small index is fetched, with a 24-hour parsed cache and the existing HTTP cache underneath; a failed refresh retains cached data and backs off. Matching requires the installed directory/package identity and a matching Decky manifest. Forks that conflict with local metadata require confirmation; observed GitHub redirects can resolve renamed repositories without a false conflict.

Confident sources are saved automatically. Uncertain matches remain **Source suggested** on the main screen and in All, with **Use this source** and **Search again** in the existing detail view. Nothing found becomes **Source not found** with **Find source**. A manual repository field is available as a fallback; it validates the Decky manifest before offering confirmation. Search names, package names and useful author hints only generate candidates, never automatic associations. Up to two manifest-matched candidates also get a compatible-release hint through the existing public release cache to order suggestions; missing releases do not exclude an otherwise matching source. No ZIP downloads or installations occur during discovery.

At most two unresolved plugins are searched automatically per backend session, after checking confidently linked plugins. Successful and empty searches are cached for 24 hours; errors back off for ten minutes in addition to existing GitHub limits. Unchanged metadata reuses saved discovery work; **Find source/Search again** can explicitly retry using the existing HTTP cache and budget handling.

Associations record directory, exact Decky display name, package identity and internal provenance. Explicit user confirmations take precedence over metadata and database hints. Automatic records are reconsidered when relevant metadata changes. Old display-name-only confirmations migrate when local project evidence agrees; otherwise they remain hints and may need one confirmation, rather than being attached to a different plugin with the same name. Settings and cache remain outside installed files and survive self-update.

Confirmed associations and HTTP cache live in Decky's plugin settings directory; staged ZIPs live in its runtime directory and expire after 24 hours during later staging. No token, additional hosted catalog, analytics, or project-operated server is involved.

## Safety and limitations

GitHub releases may not have undergone official Decky Store review. You choose whether to install every update. The updater never installs automatically, uninstalls plugins, restarts Decky, or writes installed plugin files.

Archives must have one top-level directory, valid Decky manifests, a nonempty compiled frontend, the exact installed display name, and the selected version. Traversal, links, special files, duplicate entries, encryption, corrupt contents and excessive extraction sizes are rejected. Download limit: 512 MiB; extraction limit: 2 GiB. The backend resolves tag and asset identifiers itself and accepts only GitHub HTTPS release downloads with controlled redirect hosts. When GitHub provides an asset SHA-256 digest, it is checked. A locally calculated hash alone authenticates neither the author nor the code.

Validated packages whose top-level folder differs from the installed folder are repacked to the installed folder name after verifying the original checksum and exact plugin identity/version. Package metadata, including remote_binary declarations, is preserved for the native Decky installer to handle. The native installer dependency is internal and can change. Unsupported Loader versions get a manual ZIP fallback. Local staging avoids the remote telemetry path described in Loader #984 and rejects invalid packages before handoff, but does not repair Loader's non-transactional replacement behavior (#985). There is no rollback guarantee.

Asset matching is deliberately conservative and may require a manual update for unusual names, multiple platform archives, or unrecognized tag formats. Checks inspect up to three recent SemVer releases on the first stable-release page. Public HTML parsing is isolated and refuses unrecognized page formats instead of guessing. Only public GitHub release ZIPs are supported. Automatic checks use stable releases; the manual selector also includes prereleases. Backend inventory, public release pagination and temporary staging have been exercised over SSH on a Steam Deck. The new icon placement, directional controller focus and native downgrade confirmation still require physical verification.

## Development

Use Node 22, pnpm 9.15.9, and Python 3.11 or newer. Runtime Python dependencies are all standard library.

```sh
npm install --global pnpm@9.15.9
pnpm install --frozen-lockfile
python3 -m pip install -r requirements-dev.txt
python3 -m unittest discover -s tests -v
pnpm test
pnpm typecheck
pnpm lint
python3 -m ruff check .
python3 -m ruff format --check .
```

## Building locally

```sh
bash scripts/build-local.sh
```

Produces `dist-release/Decky-Direct-Updater.zip` with the real compiled frontend and Python backend. Packaging uses an explicit allowlist and deterministic ZIP entries; no publishing occurs. Tests, settings, fixtures, source control and caches are excluded.

After building, `pnpm fixtures` creates two **local-test-only** packages and a fake release response in `dist-release/local-fixture/`. Only those special packages contain the fixed local fixture reader. The production package cannot activate it through settings, environment variables or RPC. Follow the hardware guide before using them.

## Releases

CI runs tests, checks, compilation and archive validation, then saves a build artifact. The separate release workflow runs only on deliberately pushed `vX.Y.Z` tags that exactly match both metadata versions. Only its publishing job has write permission. It creates `Decky-Direct-Updater.zip` (a stable filename for the latest-release install URL) and `SHA256SUMS` using the repository's native token.

Run `pnpm check:version` before planning a tag. Nothing bumps versions, tags commits or pushes automatically. Publish only after approving the local hardware tests. Self-update follows the public stable releases of this repository.

## References

Integration was checked against the [official template](https://github.com/SteamDeckHomebrew/decky-plugin-template), [Loader installer](https://github.com/SteamDeckHomebrew/decky-loader/blob/main/backend/decky_loader/browser.py), [Loader frontend](https://github.com/SteamDeckHomebrew/decky-loader/blob/main/frontend/src/plugin.ts), [Decktation updater](https://github.com/silverfoxy/decktation/blob/master/src/pluginUpdate.ts), and [Decky Nexus updater](https://github.com/RedRanger14/decky-nexus/blob/main/src/pluginUpdate.ts). No application boilerplate was copied wholesale.

## License

MIT. See [LICENSE](../LICENSE). The private HTML parser is vendored from CPython 3.11.14 because Decky does not bundle `html.parser`; its Python license is included in `direct_updater/_html/LICENSE`.


## Choose another version and background indicator

Open a plugin's details and choose **Install another version** to load releases from its confirmed repository. **Load more** retrieves the next page only when requested. Stable releases and prereleases are shown together; the installed version, non-SemVer tags, missing plugin ZIPs and ambiguous assets cannot be installed. Comparisons, pagination and asset resolution run in Python. A manual selection never changes an update channel or pins a version.

An older version first shows the installed and selected versions and requires **Confirm downgrade** before its ZIP is prepared. Cancel returns to the selected release without staging. After validation, Decky's own confirmation still controls the actual installation. Requests and cancellation are never reported as completed installs. Native downgrade requests use Loader's DOWNGRADE mode; all internal Loader integration remains in src/deckyInstaller.ts.

The green dot at the upper right of Direct Updater's icon in Decky's plugin list means at least one newer stable version has been confirmed. The plugin checks at load and every four hours, sharing one in-flight check and the existing backend cache with the panel. The timer and progress subscription exist even while the panel is closed, and are disposed on unload. Opening the panel or requesting installation does not clear the dot. A valid recheck reads installed versions and clears resolved updates; a failed lookup does not create an update or erase a previous positive for the same installation/source.
