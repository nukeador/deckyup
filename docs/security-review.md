# Pre-install access review

The review describes manifest declarations; it is not malware detection or a sandbox. No external scanning service, reputation score or additional binary download is involved.

## Package facts and policy

`package_validation.validate_package` extracts facts while the existing ZIP validator already has the archive and its root manifests open. Only the exact `root` flag counts as administrator access; absent optional flags and `remote_binary` declarations mean no declaration, but malformed types stop preparation. `main.py` must be a file directly inside the validated plugin root. Python code is information, not a warning on its own.

`remote_binary` names, declared URLs and optional SHA-256 hashes are parsed from `package.json`. URLs are kept internally for inspection; user-facing assessments contain only source domains, names and declared hashes. The review never follows URLs, resolves redirects or downloads the binaries. It describes what the package asks Decky to download, not every action plugin code can perform. Loader currently reads `name`, `url` and `sha256hash`: see [Loader browser.py](https://github.com/SteamDeckHomebrew/decky-loader/blob/main/backend/decky_loader/browser.py).

`security.assess_security` is the only review policy. A new installation requires acknowledgment for root or any declared executable downloads. An update or downgrade requires acknowledgment when it adds root, introduces a binary name, or changes a binary's source domain. Unchanged root, removal of root, backend presence, and same-domain version/URL-path/hash changes do not interrupt installation. When installed metadata is unreadable or malformed, the comparison is explicitly unknown. A replacement declaring root or binary downloads then requires review; if the replacement declares neither, neither type of escalation is present and no additional confirmation is required.

The optional Security details section in Plugin Details describes the installed files only, clearly labeled. It does not claim to describe an unstaged release. The authoritative assessment always comes from the selected ZIP.

## Binding and lifecycle

All staging paths, including Find Plugins, manual releases, downgrades and self-updates, use the same assessment and frontend gate. A random, session-local review token binds the assessment to the staged SHA-256, plugin identity, selected version, final folder and read-only installed identity/access snapshot. A token expires after 30 minutes and can authorize a native request only once. Before continuing, the backend rehashes the staged file and rereads installed metadata. A changed artifact, removed/replaced plugin, changed installed security declarations or new folder collision invalidates the request and deletes the staged archive. The user must prepare again. No RPC accepts an arbitrary artifact path.

Cancellation deletes the staged file and invalidates the token. Find Plugins also cancels its existing installation ticket; a cancelled review cannot persist a source association. The native installer still checks the staged checksum and asks its own confirmation. A successful request is not a completed installation. Existing installed-version verification and self-update behavior remain authoritative.

The review checkbox is in-memory and scoped to a token; it is not a remembered trust decision. Underlying screens are hidden rather than unmounted, preserving release selection, plugin detail and scroll. Cancel always receives initial focus. Compact copy keeps the essential decision visible together; unusually short panels scroll to keep the focused action reachable. B/Escape cancels, and focus returns to the initiating control. Search-result details and the review use explicit Up/Down control order, skipping hidden and disabled controls and navigation-only containers. Review actions additionally support Left/Right navigation within their row. The acknowledgment uses Decky’s native DialogCheckbox with a contrasting border and keyboard/gamepad focus highlighting; direction handlers on individual review controls do not depend on bubbling through native buttons. Repeated activation of Continue is coalesced. The integration uses Decky's existing navigation components, not a replacement installer.

This protects the application's normal flows, not a hostile plugin/frontend or a privileged process. Another installed plugin can independently invoke Decky's APIs. Loader remains responsible for confirmation and installation; this feature does not enforce filesystem permissions. There is an unavoidable interval between the final comparison and Loader's actual installation. The ZIP hash remains bound to the native request, but another external installation could change installed metadata after comparison.

## UX rationale and evidence

The design favors short consequence-based explanations, contextual change warnings, neutral routine details and a readily available Cancel action. It avoids another mandatory screen for ordinary installations or unchanged root updates. An explicit checkbox is a deliberate action, not proof of comprehension. These choices are informed by:

- [Felt et al., Android Permissions: User Attention, Comprehension, and Behavior (2012)](https://research.google/pubs/android-permissions-user-attention-comprehension-and-behavior/): low attention and comprehension motivate explaining consequences instead of merely listing technical flags.
- [Anderson et al., How Polymorphic Warnings Reduce Habituation in the Brain (2015)](https://neurosecurity.net/media/Anderson_et_al._CHI_2015.pdf): repeated warnings motivate reducing unnecessary interruptions. This implementation does not introduce polymorphic warnings or claim their experimental results.
- [Akhawe and Felt, Alice in Warningland (2013)](https://www.usenix.org/system/files/conference/usenixsecurity13/sec13-paper_akhawe.pdf): warning interaction depends on design and context.
- [Chromium Security UX](https://www.chromium.org/Home/chromium-security/enamel/) and [Mozilla, Designing Better Security Warnings](https://blog.mozilla.org/ux/2019/03/designing-better-security-warnings/): actionable explanations and understandable choices inform the presentation.

These studies do not establish the effectiveness of this plugin's implementation. Physical Steam Deck validation and user research remain separate work.

## Local validation

The browser-only fixture is `tests/fixtures/security-preview.tsx`; it and its Decky DOM adapter are excluded from production packages. The rendered review was checked in all ten languages at 350px viewport width with no horizontal overflow. React DOM tests cover initial Cancel focus, B/Escape cancellation, keyboard and mouse checkbox input, acknowledgment reset, return focus/scroll, unmount cancellation, duplicate activation, authorization mismatches and Find Plugins ticket cancellation. Backend tests include the real download/repack/assessment chain with one mocked network response.

Missing installed metadata does not relax existing identity requirements. If the installed plugin identity cannot be established, the original pipeline still blocks staging; malformed security declarations with an otherwise valid identity instead produce an unknown comparison.

## Native uninstall shortcut

The subdued Uninstall action in Plugin Details delegates to `DeckyPluginLoader.uninstallPlugin`, the same internal frontend method used by Loader's own plugin list. It opens Loader's `PluginUninstallModal`; only that native modal owns confirmation and removal. Direct Updater never calls the direct uninstall RPC or deletes an installed plugin folder. The shortcut is disabled when inventory cannot establish a unique exact manifest identity. If the method is unavailable, the UI directs the user to Decky Settings → Plugins instead of attempting another removal path. This is an undocumented Loader integration, isolated in `src/deckyInstaller.ts`; real-hardware compatibility and native cancellation still require testing.

The optional security disclosure now shows four concise items (administrator access, Python backend, flags and additional executables). A short installed-version label distinguishes inventory facts from the staged ZIP assessment. Binary names, domains and declared hashes remain inside the executable item when present.

### QAM portal regression

Read-only hardware inspection confirmed that plugin code runs in `SharedJSContext` while its controls live in `QuickAccess_uid2`. Navigation and focus restoration must use the referenced element's `ownerDocument`, not the module-global document or `instanceof` checks against the wrong window's HTMLElement constructor. Loader can mark a DialogButton with the `Disabled` CSS class while its native DOM `disabled` property is false. Directional navigation excludes that state too. Regression tests use two separate JSDOM documents and React portals to cover both navigation and return focus. Physical D-pad behavior after installing the corrected package still needs validation.
