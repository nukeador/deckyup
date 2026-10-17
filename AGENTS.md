# Development guidelines

Build and test locally. Do not push, create tags, releases, or pull requests without an explicit user request.

Keep functions small, names descriptive, dependencies minimal, and formatting consistent. Prefer straightforward functions over frameworks or speculative abstractions. Comment only non-obvious reasoning, especially security and Loader compatibility decisions. Avoid excessive logging.

Keep GitHub access, source resolution, version comparison, and archive validation in Python. Isolate all undocumented Loader frontend integration in src/deckyInstaller.ts. Never write into installed plugin folders or restart Decky. Stage and validate before requesting the native confirmation. An accepted request is not a completed install.

Treat RPC input and remote metadata as untrusted. Sources must resolve to confirmed public GitHub repositories. Never expose arbitrary URL/file staging. Preserve the exact installed plugin identity. Reject ambiguous assets. Automatic updates must use newer stable versions only. Older versions and prereleases are permitted exclusively through manual release selection; downgrades require an explicit warning and confirmation before staging, bound to the installed version shown.

Persistent state belongs in Decky's settings/runtime directories. Development fixture behavior must be absent from production packages. Self-update must use the generic pipeline.

Before delivery run Python and frontend tests, type checking, formatting checks, frontend build, package validation, and version consistency checks. Document hardware-only checks honestly. See docs/steam-deck-testing.md.

Source discovery must reuse GitHub request caching/backoff, prioritize linked release checks, and limit automatic searches to two unresolved plugins per backend session. Persist associations against directory and exact manifest/package identity; confirmed user choices take precedence. Conflicting forks and search results require explicit selection. Discovery must never stage or install packages.
