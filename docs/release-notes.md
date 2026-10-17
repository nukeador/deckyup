Update your installed Decky plugins directly from their developers, without downloading each ZIP by hand.

### Install once

Enable **Developer Mode** in **Decky → Settings → General**, then open **Developer** and install from this URL:

```text
https://github.com/nukeador/decky-direct-updater/releases/latest/download/Decky-Direct-Updater.zip
```

Or download **Decky-Direct-Updater.zip** below and use **Install Plugin from ZIP**.

### Included

- Automatic source discovery from plugin metadata and the official Decky plugin database.
- Repository suggestions on the main screen, marked with a question icon and confirmed with **Use this source**.
- Stable update checks at startup and every four hours, with a green dot on Direct Updater's icon.
- A version picker for prereleases and older versions, with an explicit downgrade warning.
- Updates for Direct Updater itself through the same confirmation flow.

Updates always require your approval. A plugin needs a compatible GitHub release ZIP; otherwise use the Decky Store.

Local validation: Python/frontend tests, types, formatting, build and package validation. Physical controller behavior, virtual keyboard and native downgrade confirmation still need broader Steam Deck testing.
