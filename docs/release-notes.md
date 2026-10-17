Update your installed Decky plugins directly from their developers, without downloading each ZIP by hand.

### Install once

Enable **Developer Mode** in **Decky → Settings → General**, then open **Developer** and install from this URL:

```text
https://github.com/nukeador/deckyup/releases/latest/download/Decky-Direct-Updater.zip
```

Or download **Decky-Direct-Updater.zip** below and use **Install Plugin from ZIP**.

### v0.1.8

- **Clear all-updated state:** when every installed plugin is current, the Updates tab now displays a large centered green check and "You're up to date" message.
- Other states, including pending checks, failed checks and unknown sources, continue to show their specific guidance.

### v0.1.7

- **Self-update panel refresh:** after Decky confirms the new installed version, close the old quick-access panel and reopen the Decky tab so the updated interface is shown.
- Cancelled or failed self-updates do not trigger a panel reopen.

### v0.1.6

- **Safer updates:** reject update archives whose internal package identity differs from the installed plugin.
- **More reliable GitHub release discovery:** inspect subsequent stable releases when a newer release has ambiguous assets, while continuing to reject unsafe automatic selections.

### v0.1.5

- **Update directly from the list:** select the download icon beside a plugin in Updates or All to prepare its update and open Decky's native confirmation. The name still opens details.
- A loading indicator shows preparation, and repeated presses cannot prepare duplicate updates.
- **Find and install:** the README now includes real Steam Deck screenshots of repository search and installation details, with quick instructions.

Find Plugins, cached GitHub search, repository descriptions, stable update checks, manual version selection and self-updates remain available.

Updates always require your approval. Licensed under GNU AGPL v3.
