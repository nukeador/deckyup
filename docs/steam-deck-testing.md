# Local Steam Deck testing

Hardware validation is pending. These instructions do not deploy to a Deck automatically. Use the fixture packages for the first replacement test, rather than an important installed plugin. Production packages and fixture packages have the same identity: installing either replaces the other.

## Build and transfer

On the development computer, from the repository:

```sh
pnpm install --frozen-lockfile
bash scripts/build-local.sh
pnpm fixtures
```

Transfer `dist-release/Decky-Direct-Updater.zip` and the entire `dist-release/local-fixture/` directory to the Deck's Downloads directory using a USB drive, KDE Connect, or a transfer method you already use. Do not unpack the installable ZIPs. The normal production ZIP has no fixture mechanism.

Optional SSH transfer, only if you have already enabled and tested SSH:

```sh
scp dist-release/Decky-Direct-Updater.zip YOUR_USER@YOUR_DECK:Downloads/
scp -r dist-release/local-fixture YOUR_USER@YOUR_DECK:Downloads/
```

Replace the placeholders with your actual account and host. No root or remote service restart is required. Do not use a deployment script that replaces installed plugin directories.

## Install the normal build

1. Return to Gaming Mode and open QAM with **…**.
2. Select Decky's plug icon, open its gear/settings, and enable **Developer Mode** in **General** if the developer section is hidden. Labels can differ across Loader versions.
3. Open Decky's **Developer** section, choose **Install Plugin from ZIP**, navigate to Downloads, and select `Decky-Direct-Updater.zip`.
4. Review and accept Decky's installation prompt. Reopen QAM → Decky → **Decky Direct Updater** after it loads.
5. Select **All** and confirm the list contains your installed plugins, including any disabled ones. Compare versions against their installed `package.json` (Decky uses that version). A malformed plugin must not hide the others.
6. Confirm the updater finds its own GitHub source. Older package metadata may still name `nukeador/decky-direct-updater`; GitHub redirects that repository to `nukeador/deckyup`. For the no-release case, use a test repository with no published releases; it must not show a fatal error just because that repository has no releases.

If your Loader does not expose manual ZIP installation or the installer API used here, update Loader through its own supported flow or consult its documentation. The plugin must give a manual ZIP fallback instead of changing folders directly.

## Check detection and interaction

- If Decktation is installed, verify `silverfoxy/decktation` appears without text input.
- If MAKO is installed, verify **MAKO - Frame Generation**, its installed version, and `eugeniosegala/MAKO`. Package name `mako-plugin`, repository name and display name may differ.
- For a plugin with no source, select **Find source** using the controller. Candidate repositories must have an exact matching root or `plugin/plugin.json` manifest. If several match, select the intended author yourself with **Follow owner/repo**. Back out without selecting and verify no mapping was silently saved.
- Reopen the panel and restart Decky through its normal UI if desired; confirmed sources must survive. Confirm settings are outside the installed plugin folder.
- With Wi-Fi disabled, open the panel: local plugins must remain visible. A cached result may still appear. Wait at least one minute after the previous check, then press **Check for updates** to force revalidation: failures must say **Could not check for updates**, never **Up to date**. Restore Wi-Fi and retry.
- A plugin equal to or ahead of its stable release should be **Up to date**. Missing archives and unknown versions should have their own unavailable status.
- Navigate the entire list, source choices and buttons with the D-pad/joystick and A/B. Verify focus visibility, long names, QAM scrolling and readable errors.

## Controlled self-update: 0.1.0 → 0.1.1

These are explicit development builds with a fixed local data reader. No local HTTP server, token or published GitHub release is needed. The only production component replaced is the release/download provider; release selection, semantic comparison, archive validation, staging and the native installer adapter are exercised.

1. In Desktop Mode, locate Decky's home folder. Use the directory containing its existing `plugins`, `settings`, `data` and `logs` directories; do not assume a username. The plugin runtime path is exposed to its backend as `DECKY_PLUGIN_RUNTIME_DIR`. For the packaged folder `decky-direct-updater`, it normally ends in `data/decky-direct-updater`.
2. Create `local-fixture` inside that runtime directory. Copy `release.json` and `Decky-Direct-Updater-v0.1.1.zip` from the transferred local fixture directory into it. Leave the ZIP intact. Example, after substituting your actual Decky home:

   ```sh
   DECKY_TEST_HOME='/actual/path/to/homebrew'
   mkdir -p "$DECKY_TEST_HOME/data/decky-direct-updater/local-fixture"
   cp "$HOME/Downloads/local-fixture/release.json" \
      "$HOME/Downloads/local-fixture/Decky-Direct-Updater-v0.1.1.zip" \
      "$DECKY_TEST_HOME/data/decky-direct-updater/local-fixture/"
   ```

3. In Gaming Mode install `Downloads/local-fixture/Decky-Direct-Updater-v0.1.0.zip` using Decky's manual ZIP installation. Confirm **Installed: 0.1.0** and **Latest: 0.1.1** in the updater panel. Missing fixture files should produce an error, not fall back to an arbitrary download.
4. If possible, confirm an unresolved plugin's source before upgrading. For a deterministic persistence probe, in Desktop Mode with the panel closed, add a harmless `"hardware_test_marker": "preserve-me"` top-level key to the existing settings `state.json` without changing `sources` or `cache`. Keep a backup. Its path normally ends in `settings/decky-direct-updater/state.json`.
5. Press **Update** for **Decky Direct Updater**. Verify Decky's native prompt shows the correct plugin, version 0.1.1 and an update action. **Cancel** it. Reopen the panel and check again: installed version must remain 0.1.0; the updater must not claim success. The Update button must remain usable.
6. Press **Update** again and **accept**. The updater may unload itself. Wait for Decky to reload it, then reopen QAM and verify **Installed: 0.1.1** and **Up to date**. Do not depend on the previous frontend instance remaining active.
7. Recheck the saved source mapping and optional marker in the persistent settings file. Both should remain. Check logs for errors.
8. Reinstall the normal production `Decky-Direct-Updater.zip` through Decky after the experiment; use its actual release version when deciding whether this is an upgrade, reinstall or downgrade. Remove the `local-fixture` runtime subdirectory when finished. The normal ZIP cannot read those fixtures.

To repeat, reinstall the 0.1.0 fixture ZIP manually. Never publish these fixture ZIPs or their fake release response. Fixture files are absent from the production ZIP and release workflow inputs.

## Logs and recovery

Decky exposes the plugin's log directory as `DECKY_PLUGIN_LOG_DIR`, normally under its home at `logs/decky-direct-updater/`. Inspect the newest log in Desktop Mode. If SSH is already available, you can read that exact path remotely. Loader logs may be available in its normal troubleshooting UI or, on a systemd installation, with `journalctl -u plugin_loader --since '15 minutes ago'` if your account has permission. Do not assume root access.

A refused archive has not been handed to Loader and should leave the installed plugin intact. Loader can still fail after confirmation; its replacement process is not transactional and this updater cannot guarantee rollback. Keep the known-good ZIP locally. Reinstall it through **Install Plugin from ZIP** if a plugin fails to load. If Decky itself stops working, follow Decky's official recovery procedure rather than manually editing plugins or restarting services from this project.

Staged ZIPs remain available through confirmation and installation. Files older than 24 hours are cleaned on a later staging operation; canceling a prompt does not immediately remove them.

Record Loader/SteamOS versions, the ZIP tested, controller behavior, observed source associations, canceled/accepted upgrade results and logs before approving any release.

## GitHub limits regression

Release checks, raw manifest validation and release downloads should continue without consuming GitHub REST core quota. Repository search uses its separate search quota and can still require a short wait. Repeated refreshes within one minute reuse cached results. An exhausted quota must show a retry delay rather than a Python exception.

Confirm HelixSR Manager resolves its HelixSR-Manager.zip asset despite its different package name. Test preparing TabMaster only after the controlled fixture upgrade; cancellation must remain possible. Preparing an already listed update uses cached source metadata and must not force another REST release lookup.

## Compact interface regression

The default **Updates** view contains confirmed pending updates and unresolved sources with a question icon. Its count and the green dot still represent only actual updates. **All** includes every plugin and places updates first. Each row should remain two lines, with an ellipsis for long names and one status icon. Open a row to access its source and actions; selecting a row must never request an installation.

Using the physical controller, test D-pad navigation and A to open details. Press B to return from details, including after following a source. The same row and scroll position should be restored. Scroll well down All, visit Updates, then return to All: both views should retain their own position. The compact segments use normal directional focus; no custom L1/R1 shortcut is implemented.

Use the refresh icon while looking at a long list. Existing rows should remain visible and navigable; individual results arrive progressively, followed by the reconciled final result. Check that focus and scroll do not reset when those results arrive. Test Retry in a failed plugin's details, Find source for an unresolved plugin, Change source for a followed plugin, and Update only in confirmed update details. A prompt request must not be labeled as a completed installation.

Browser checks use simulated Decky primitives. Physical B handling, D-pad scrolling, the native focus ring, touch, and SteamOS font scaling still require validation on the Deck.

## Frozen Python and navigation groups

The installable ZIP includes CPython's HTML parser, entity table and markup base with their license. A subprocess regression blocks the system `html` and `_markupbase` modules and imports the parser directly from the packaged ZIP. Source search and release checks must not depend on those optional Decky stdlib modules.

On hardware, start with Updates, press Right through All to the refresh icon, then Left back. Move Down into All's list, and Up from its first row back to the header. Repeat after a refresh and after returning from details. Containers now declare native row/column flow and are not themselves focus targets. Physical controller verification remains required.

## Release and layout regressions

Verify CSS Loader resolves its repository despite stale template homepage links. A confirmed source must clear old conflict warnings. SteamGridDB should report no stable GitHub release when its source has none. Refreshes reuse cached parsed releases and check independent repositories concurrently.

Open long details in the short QAM viewport and scroll through every action. Focused header controls must look distinct from the selected tab. Check these with the physical controller.

Prepare an LSFG update and cancel the native installer confirmation first. A differing ZIP root must be normalized to the installed folder after identity/version/checksum validation. The package.json bytes, including remote_binary declarations, must be preserved for Decky to handle normally. Only accept the upgrade when ready to test it; preparation alone must not change installed files.

## Manual releases and downgrade confirmation

Local tests cover stable and prerelease SemVer (`dev`, `beta`, `rc`), non-comparable tags, missing and ambiguous ZIPs, both GitHub pagination formats, opaque frontend cursors, stale installed versions, changed sources, forged identifiers, manipulated release metadata, ZIP identity/version mismatches and confirmed downgrade staging. The same pipeline is tested using Direct Updater's own plugin identity. The UI store tests cover initial/four-hour checks without the panel, single-flight requests, progress, preserved positive results after errors, canonical source redirects and disposal.

On the physical Deck (pending validation of the newly added UI):

1. Open a plugin with a confirmed source, then **Install another version**. Use D-pad/A/B through releases and **Load more**, including a second/last page, slow loading and a failed load followed by Retry. Existing releases and scroll position should remain usable. Focus should stay on Load more, or move to the first newly loaded row when there are no further pages.
2. Check the installed version is labeled and disabled, prereleases are labeled, and incompatible/ambiguous entries explain why they are disabled. A source without releases should display an empty result. Tags such as `nightly` must not become installable.
3. Select an older version. Verify both versions appear in the warning. Initial focus is on Cancel. Cancel or B must stage nothing and return focus/scroll to that release. Explicit confirmation may prepare the ZIP, followed by Decky's own downgrade prompt. Cancel that native prompt and recheck: the installed version must remain unchanged.
4. Accept a controlled upgrade/downgrade only when ready. Read back the actually installed version after refreshing. A message saying **Confirmation requested** must never say installation completed. Choosing a prerelease must not subscribe to prereleases or pin it; Update and automatic checks still select newer stable releases only.
5. Repeat the existing local self-update fixture procedure (0.1.0 → 0.1.1), including cancellation. Direct Updater must reload using the same installer path as any other plugin. Actual self-install and native confirmation remain hardware checks, not automatic installation tests.
6. Return to Decky's general plugin list. Verify the green dot is attached to Direct Updater's icon at its upper right. It should appear after a successful background check with the panel closed, persist after opening the panel or requesting/canceling an update, survive a later failed lookup, and disappear after a valid recheck finds no pending stable updates. Test again after restarting/reloading the plugin. Physical icon placement is pending.
7. Leave the panel closed for four hours (or use a development-only shortened timer outside the production package) and verify the next check runs once. Opening/refreshing during a check must reuse it. Unload/reload and ensure old timers/listeners no longer issue checks or update the UI.

Browser validation uses simulated Decky controls and a native-installer stub. It can verify key activation/Escape, focus restoration, loading/error states, paging, warning cancellation, shared badge state and request arguments. Steam's directional focus behavior and actual Loader prompts require the physical checks above.

## Plug-and-play discovery

Automated tests use mocked network responses for first launch, local repository and secondary/plugin.json hints, official database matching, conflicting forks and redirects, confirmed precedence, negative/positive search caching, new/removed plugins, metadata changes, reused directories, legacy hints, offline behavior/backoff, search quota errors, author-qualified searches, manual entry verification and rejected candidate identifiers. They assert that discovery does not download/stage/install anything and that normal self-update preserves settings.

Physical checks for this feature remain pending:

1. Back up Direct Updater's settings, then test a fresh settings directory using Decky's supported setup. Open Direct Updater: local inventory should appear immediately and confident sources should be checked without an initial detection button. Keep unresolved plugins visible in All. No modal or installation prompt should appear.
2. Open a suggested plugin, navigate to one of the candidate repositories with D-pad/A and select **Use this source**. Its release status should update and survive reopening/reloading. Try multiple candidates, Search again, a missing match and Enter repository → Verify source → Use this source. Verifying alone must not associate or install anything.
3. Install/remove a separate test plugin through Decky's UI and reopen the panel. The inventory should reflect it, without losing prior confirmed sources or redoing unchanged searches. Repeated openings should reuse GitHub caches; stable update checks remain prioritized ahead of automatic searches.
4. Test a known fork whose local metadata differs from the official database. The updater must ask you to choose, not silently switch it. After confirmation, changing local repository hints or refreshing the upstream index must not override the confirmed mapping.
5. Disconnect networking. Installed plugins and valid cached mappings should remain available; lookup errors belong to the affected plugin. Reconnect and retry through Find source. A rate limit must preserve its retry message, not surface a Python exception or initiate a burst of searches.
6. Perform the existing controlled self-update fixture test and verify confirmed associations survive. Older name-only mappings without sufficient local identity evidence may appear as suggestions once; their stored values are retained until reviewed.

A read-only SSH smoke test with isolated temporary settings exercised actual installed metadata and upstream discovery. It does not verify Steam's directional focus, virtual keyboard or live installer behavior. Do not delete real settings or replace installed plugin directories to run development diagnostics.

README screenshots were captured from the running Direct Updater panel on a Steam Deck through its local CEF debugger, cropped to the plugin panel and visually checked to exclude account names, avatars, notifications and other desktop content. They show pending updates and plugin details; no installation was started to obtain them.

## Find Plugins acceptance checks

Install the local ZIP from Downloads yourself, through Decky's Developer settings. This build has not been published to GitHub.

1. Open Direct Updater. Use Right/Left/Up/Down to reach the Search icon immediately before Refresh; confirm that Updates, All and Refresh still work.
2. Open Search with A. Type `MAKO` using the SteamOS keyboard; dismissing the keyboard must keep the view open. No search starts until Search/Enter is submitted. Confirm five two-line rows, stars aligned right and Fork labels where returned.
3. Choose Show more. Confirm five extra rows appear without a new search while cached results remain. Test a long repository name and scrolling near the bottom.
4. Open one result with A; verify compact details, compatible stable release, GitHub link and appropriate Install/Update/Up to date state. Opening it must not request installation. Press B: query, results, visible count, scroll and focused result must be preserved. B again returns to the previous main tab; reopening Search retains the search.
5. Try `silverfoxy/decktation` and `https://github.com/silverfoxy/decktation`. Both should open the intended repository directly, using at most one uncached repository lookup rather than broad search. Repeat a name search to exercise the cache.
6. For a plugin you want to install, select Install. Read Decky's native prompt and cancel first. Return to search: it must not claim success or save a confirmed association. If needed choose I cancelled in Decky to clear the pending request.
7. Repeat and accept. After Decky completes, verify the success status and that All contains one plugin with the actual installed version and confirmed selected source. If the Loader event is unavailable, use Check installation. It must stay unconfirmed until the actual files/version are present.
8. Search for an installed plugin: same source/newer stable should offer Update; current or newer installed version should show Up to date; unknown versions or a different source must not overwrite it. Test native update cancellation too.
9. Verify an unsupported repository, a fork, archived/disabled projects, network-offline details and a search rate limit. Existing Updates/All must remain usable; short errors should replace raw exceptions. Cached results should remain available where present.
10. Check the generic self-update flow with a later compatible test release when available. Reloading Direct Updater during installation drops its runtime pending ticket; check actual version in All afterward. No success must be inferred from merely opening/accepting the prompt.

Pending physical checks: directional focus including keyboard dismissal, touch, scroll/focus retention in QAM, native INSTALL/UPDATE prompts and cancellation, successful new plugin installation/source tracking, and self-update reload. Browser mocks do not certify these. Technical logs use existing debug logging categories (search/repository/release metadata, cache hits and rate limits), with no secrets or telemetry.

## Quick update actions

In both Updates and All, activate the plugin name to open details, or move Right to its download icon and press A to prepare the update directly. The icon shows a spinner while preparing; repeated presses must not prepare another ZIP. Decky still asks for confirmation. Cancel must not report success or clear the update indicator. Check touch targets, Left/Right focus, long names, scroll retention and errors from the list. Non-update status icons remain part of the Details action. These physical checks remain pending.

## Pre-install access review (hardware validation pending)

Local tests emulate Decky gamepad events in a DOM; they cannot certify Steam's actual focus routing, screen-reader behavior or native installer integration. On hardware, use disposable test plugins and exercise each entry point: list update, details update, version selector (including a prerelease and an explicitly confirmed downgrade), Find Plugins install/update, and self-update.

- Prepare a package with no root or binary declarations: only the normal Decky confirmation should appear. Optional Security details must identify the installed version, not claim to describe an unstaged release.
- Prepare a package adding the exact `root` flag: verify a short administrator-access explanation and old/new comparison. `_root` alone must not trigger this warning.
- Hold/repeatedly press A from the originating install/update control: initial review focus must be Cancel when visible, or the inactive heading for a long warning; Continue stays disabled before the checkbox is deliberately checked. Press B and check that the same plugin/release, list scroll and originating focus are restored. Repeat using keyboard Escape/Space/Enter, mouse and touch.
- Confirm root unchanged and same-name/same-domain binary updates do not add a review. A new binary name or changed domain must trigger review. Verify long German/French/Spanish text wraps at QAM width and all controls remain reachable without horizontal scrolling.
- Cancel a Find Plugins security review: no native prompt, staged ZIP or remembered association should remain. Prepare again and accept the review: Decky's original prompt must still appear, and cancelling there must not report success.
- With a review open, change the disposable installed manifest or staged ZIP. Continuing must stop with a localized error and require fresh preparation. Do not modify installed production plugins for this check.
- After a genuine completed self-update, the old panel should close and Decky's updated panel reopen. Neither cancelling the review nor cancelling Decky's prompt should count as a completed installation.

## Published self-update test: 0.2.1 → 0.2.2

1. Download the ZIP specifically from [v0.2.1](https://github.com/nukeador/deckyup/releases/tag/v0.2.1) and install it through Decky’s native ZIP option. Do not use the latest-release URL to establish this starting version.
2. Close and reopen Quick Access once after this initial installation. Confirm the installed version is **0.2.1**, then refresh Direct Updater to detect **0.2.2**.
3. Select Update for Direct Updater. First cancel Decky’s native confirmation: the installed version must remain 0.2.1 and no completed-update reopen should occur.
4. Request the update again and accept Decky’s native confirmation. Once Loader replaces the frontend, Quick Access should close and reopen with the normal plugin view. The previous download/preparation screen must not return.
5. Check Direct Updater in **All**: installed version **0.2.2**, with no update offered for Direct Updater. Other plugins can still have updates. Confirm saved source choices remain intact.
6. If the panel remains stale, record the visible installed version and exact screen before closing it, and collect the plugin/Loader logs from [Logs and recovery](#logs-and-recovery). Do not edit installed plugin files or restart services to force a passing result.

Publication makes this path available; the real native completion and panel replacement still require physical Steam Deck validation.

## Self-update frontend handoff regression

- Install the corrected build, then update through its native flow to a different fixture version. The requesting instance must not reopen QAM merely because the new files are visible. Only the replacement frontend matching the target version may consume the pending handoff.
- Repeat a downgrade and cancellation. Cancelled native prompts must not reopen the panel as a completed install.
- Unloading during inventory verification must preserve the marker for the replacement; unloading after closing QAM must cancel the delayed reopen.
- The fixture builder now rebuilds each frontend against its fixture manifest version, then restores both project manifests and the normal frontend build.
- The first transition from an older unpatched frontend still runs that frontend's existing handler. If it reopens a stale view during this transition, close and reopen QAM manually; subsequent transitions must be tested from the corrected build. Do not restart Decky or write into installed plugin directories.


### Confirmed stale-panel cause

Hardware inspection found installed files and Loader’s registered plugin at 0.2.2 while Loader’s active plugin object still referenced 0.2.1. Clearing the active selection and selecting the registered replacement through Loader’s methods changed the visible screen from the pending update to “Todo actualizado”, without reinstalling or restarting Decky. This directly validates the selection repair; the complete native 0.2.1 → 0.2.2 installation sequence still needs a run with both corrected packages.


### Repeated same-version registration

A second hardware capture showed two different 0.2.2 instances: the registered store had completed its check, while the selected panel referenced a disposed store frozen with `checking=true`. The repair must compare content identity, not just the version string, and remain available after the initial handoff marker is consumed. Re-selecting the registered content restored “Todo actualizado”; registered, selected and displayed store references then matched. Regression tests cover a second registration, rejecting work from a superseded instance and preserving focus when another plugin is selected.
