# Website and permanent installer

The static website lives in `site/index.html`, `site/styles.css`, `site/script.js`, `site/language.js` and the dictionaries in `site/locales/`. It uses local system fonts, real unchanged Steam Deck screenshots and no framework, external requests, tracking or cookies. Pending updates and plugin details are the main visual; the copy explains automatic installed-plugin/source discovery and displays the Find Plugins screenshot. Source discovery may need the user's confirmation and cannot resolve every plugin.

Public addresses:

- Website: https://deckyup.nukeador.com/
- Installer: https://deckyup.nukeador.com/install.zip
- GitHub Pages fallback: https://nukeador.github.io/decky-direct-updater/

## Build and preview locally

```sh
python3 scripts/build-pages.py
python3 -m http.server 8766 --directory _site
```

The build makes three public GitHub requests: latest stable release metadata, the named ZIP, and `SHA256SUMS`. It does not rebuild the plugin. Drafts, prereleases, missing/duplicate assets, unexpected asset URLs, checksum mismatches, oversized downloads and invalid Decky packages fail the build. The existing package validator reads the archive without executing its contents. `_site/install.zip` is copied byte for byte from the verified release. Failed verification leaves previous local output untouched, but fails the workflow so nothing is uploaded or deployed.

`_site/` and temporary `.pages-*` folders are ignored by Git. Images are copied from `docs/images/`; their originals are not modified. The `site/CNAME` file keeps the custom domain attached to the Pages deployment. The visible installation field, both Copy buttons and both download links use the same public installer. Navigation and image links are relative, so they work on the custom domain and in the local project-subpath preview. Copy success has a live status region; unavailable/denied clipboard access selects the visible URL for manual copying. Downloading and reading the instructions work with the script disabled. Screenshot links open the original image for a closer look on small screens.

## GitHub Pages publishing

The `Website on GitHub Pages` workflow publishes the static site and the verified stable release ZIP. The repository's Pages source should be **GitHub Actions** and its custom domain should be `deckyup.nukeador.com`. Keep the DNS records for the domain pointed at GitHub Pages. The workflow does not create releases or modify repository settings.

If Pages has not been enabled yet, use **Repository Settings → Pages → Build and deployment → Source: GitHub Actions**, then run **Website on GitHub Pages** on `main`. Allow the `github-pages` deployment environment if the repository requires approval. After deployment, check the custom-domain homepage and installer.

The separate `pages.yml` workflow runs on website/build-script/referenced-image changes to `main`, manual dispatch, and completion of **Deliberate version release**. Failed release runs, PR-triggered runs and runs from another repository are skipped. A successful trusted tag release refreshes the installer even though its release was created with `GITHUB_TOKEN`; it does not rely on the `release: published` event. Existing CI and tag-release workflows are unchanged.

The build always checks out trusted `main` without persisted credentials and resolves the latest stable release at build time. It never executes downloaded release code or artifacts from the triggering workflow. Build permissions are `contents: read` and `pages: read`; only deployment receives `pages: write` and `id-token: write`. One concurrency group serializes deployments without cancelling an active deployment. Nothing commits generated files or creates plugin releases.

The actions follow GitHub's [custom Pages workflow](https://docs.github.com/en/pages/getting-started-with-github-pages/using-custom-workflows-with-github-pages) architecture. Current upstream majors were verified when implementing: checkout v7, configure-pages v6, upload-pages-artifact v5 and deploy-pages v5.

## Validation

```sh
python3 -m unittest discover -s tests -q
pnpm test
pnpm typecheck
pnpm lint
pnpm exec prettier --check site .github/workflows/pages.yml
python3 -m ruff check .
python3 -m ruff format --check .
bash scripts/build-local.sh
python3 scripts/check-version.py
python3 scripts/build-pages.py
python3 scripts/validate-package.py _site/install.zip 0.1.5
```

The last version argument must match the downloaded stable release (printed by build-pages), even if local plugin metadata is newer. Website tests use mocked releases and test missing/duplicate/untrusted assets, drafts/prereleases, corrupt downloads, HTML masquerading as a ZIP, package structure, unchanged installer bytes, balanced HTML, project-relative links, image alt text/dimensions and workflow guards.

Browser validation uses the built site under `/decky-direct-updater/`. Checks include 320, 375, 768 and 1280-pixel widths (including a 1280×800 Steam Deck-sized viewport), screenshot loading, overflow, keyboard focus, copy feedback without navigation, denied/unavailable clipboard fallback, and a real local ZIP download. Desktop and mobile screenshots are inspected. A run with the site script blocked verifies the static instructions, URL and download links remain available; it does not claim a physical Steam Deck browser test.

Before publication, the build was exercised against the real stable v0.1.5 release. The copied installer checksum was `a1e189769f3a690abd0961c770118e128c0c9dc00a5269518b94b96d3a4e6649`. Normal future builds resolve a fresh release instead of pinning that version or digest.

Installation labels were checked against Decky Loader's current [general settings](https://github.com/SteamDeckHomebrew/decky-loader/blob/main/frontend/src/components/settings/pages/general/index.tsx), [developer settings](https://github.com/SteamDeckHomebrew/decky-loader/blob/main/frontend/src/components/settings/pages/developer/index.tsx) and English translation: Developer mode under General; Install Plugin from URL with an Install button; Install Plugin from ZIP File with Browse. Wording can vary by Loader language/version. Bazzite is not advertised because this project's testing does not establish it.

## Public smoke test after deployment

Run these checks after a Pages deployment:

```sh
mkdir -p /tmp/ddu-pages-check
curl --fail --location https://deckyup.nukeador.com/ -o /tmp/ddu-pages-check/index.html
curl --fail --location https://deckyup.nukeador.com/install.zip -o /tmp/ddu-pages-check/Decky-Direct-Updater.zip
gh release download --repo nukeador/decky-direct-updater --pattern SHA256SUMS --dir /tmp/ddu-pages-check --clobber
(cd /tmp/ddu-pages-check && shasum -a 256 -c SHA256SUMS)
python3 scripts/validate-package.py /tmp/ddu-pages-check/Decky-Direct-Updater.zip 0.1.5
```

Use the actual latest release version for the last command. Then open the public page on a Steam Deck, test Copy/Download, and install the URL through Decky's native confirmation. A real Pages deployment, deployed URL/checksum checks, release-to-Pages synchronization and installation from the public URL cannot be certified by the local preview.

## Languages, icon and the three use cases

The page now presents **Stay up to date**, **Find & install plugins**, and **Built for plugin developers, too**. The real search screenshot is displayed beside the latter two explanations, not hidden behind a link. Existing pending-update and detail screenshots remain prominent. The plugin runtime and its interface language are unchanged; screenshots retain their original English text.

The language system follows Decktation's website behavior: complete static pages, a native selector, a stored language preference, browser-language detection only on the default entry route, and an English fallback. It reuses that approach without bringing Astro or a client-side framework into this project. `scripts/site_locales.py` renders the shared template from `site/locales/*.json`. Missing/empty keys fail the build rather than producing mixed-language pages. Values are HTML-escaped, including metadata, labels, status messages and image alternatives.

Routes are `/en/`, `/zh/`, `/ru/`, `/es/`, `/pt/`, `/de/`, `/ja/`, `/fr/`, `/pl/` and `/ko/` on the custom domain. The root is also English and performs optional preference detection. `/en/` is an explicit English route, so an English selection still works when local storage is blocked. Canonical/hreflang metadata identifies the language; Portuguese uses the general `pt` tag and Chinese uses `zh-Hans`. Every Portuguese regional browser tag and saved preference maps to the same Portuguese page. Chinese variants use Simplified Chinese. Explicit localized URLs retain their language regardless of saved preference. Changes preserve query strings and fragments. Only the language code is saved locally; there are no cookies or analytics.

All pages point to the single root `install.zip`, including without JavaScript. A no-script language link list complements the JavaScript selector. No extra installer copies or translation-network requests are made.

The ten languages were selected from Valve's [Steam Hardware & Software Survey, September 2026, combined platforms](https://store.steampowered.com/hwsurvey/Steam-Hardware-Software-Survey-Welcome-to-Steam), checked on 17 October 2026: English, Simplified Chinese, Russian, Spanish (Spain), Portuguese, German, Japanese, French, Polish and Korean. This is a survey snapshot, not a permanent ranking or a Linux-only audience estimate. Adding another language requires a reviewed dictionary, not an automatic machine-translation request during deployment.

Both GitHub links use the official locally vendored **Font Awesome Free 6.7.2 GitHub SVG**, with an accessible GitHub name and the original attribution/license in `site/vendor/fontawesome/`. A single SVG avoids downloading Decktation's full icon font or contacting a CDN.

### Editorial review

The translations were written for the condensed page, then reviewed again after adding the three product use cases. The review checks meaning, native phrasing, consistent address, practical installation terminology, punctuation, text expansion and the distinction between finding an update and installing it. It does not claim an independent review by ten human native speakers.

- **English:** concise utility language; stable versions, source lookup and user-controlled installation remain distinct.
- **Spanish:** consistent informal singular; “con el mando” and “sin salir del modo de juego” rather than literal English gaming phrases.
- **Portuguese:** one `pt` page serves every regional variant. The copy avoids Brazil-only terms such as “baixar” and “controle” and favors wording that reads naturally across Portuguese-speaking regions.
- **German:** replaced the stiff “Auch nach eigenen Updates sucht das Plugin selbst” with “Es prüft auch, ob es selbst ein Update gibt”; consistent “du” and official installation labels.
- **French:** consistent “vous”, nonbreaking spaces before French punctuation, and the existing URL-installation label quoted as a UI label rather than treating its awkward wording as normal prose.
- **Russian:** stable releases and voluntary updates are explicit; the menu name was corrected from a generic “Общие” to Decky's actual “Общее”.
- **Polish:** replaced literal “at a glance” wording with “Twoje wtyczki zawsze aktualne”; natural GitHub inflections and controller terminology.
- **Simplified Chinese:** concise native punctuation and phrasing; corrected the General menu to Decky's “通用”. No Western separator spaces are inserted around the ZIP link.
- **Japanese:** complete natural clauses, standard polite instructions and native headline phrasing; no forced spaces between Japanese ZIP-link fragments.
- **Korean:** shortened the mechanically repeated search/install/update verbs to “검색·설치·업데이트”; consistent polite guidance and word-aware wrapping.

Automated checks cover dictionary completeness, unresolved tokens, all localized routes and assets, metadata alternatives and the single installer. Browser checks verify all ten languages at 320px without overflow, actual route switching with query/hash preservation, saved preferences, explicit-language precedence, explicit English with blocked storage, localized Copy feedback and all three screenshot elements. Desktop/mobile rendering is inspected separately. Linguistic feedback from users remains welcome; language completeness tests cannot establish fluency on their own.
