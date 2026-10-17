# Decky Direct Updater

Update your installed Decky plugins directly from their developers on GitHub.

## Install

You need [Decky Loader](https://decky.xyz/) on your Steam Deck.

1. Open **Decky → Settings → General** and enable **Developer Mode**.
2. Open the **Developer** tab and install using either option:
   - **URL:** paste the address below into **Install Plugin from URL** and confirm.
   - **ZIP:** [download the latest ZIP](https://github.com/nukeador/decky-direct-updater/releases/latest/download/Decky-Direct-Updater.zip), then select it with **Install Plugin from ZIP**.
3. Open **Direct Updater**. It finds your installed plugins and checks for updates automatically.

```text
https://github.com/nukeador/decky-direct-updater/releases/latest/download/Decky-Direct-Updater.zip
```

## Use it

- **Update available:** open the plugin and choose **Update**. Decky asks you to confirm the installation.
- **Question mark:** the source needs your attention. Open it and choose **Use this source** for a suggested repository, or **Find source**. These plugins appear on the main screen, so you do not need to look in **All**.
- **Green dot on the Direct Updater icon:** a stable update is available. Checks run when the plugin loads and every four hours; you can also refresh manually.
- **Install another version:** choose a prerelease or an older version. Downgrades ask for an extra confirmation.

Direct Updater also checks for **its own updates**, so you only need the installation URL once. It never installs updates without your confirmation.

Plugins need a compatible ZIP release on GitHub. Plugins without one, such as SteamGridDB, should be updated through the Decky Store. Releases from developers may not have the Store's review.

## On Steam Deck

<p>
  <img src="docs/images/updates.png" width="300" alt="Direct Updater on Steam Deck showing available plugin updates" />
  <img src="docs/images/plugin-details.png" width="300" alt="Plugin details with installed and latest versions and the Update button" />
</p>

[Latest release](https://github.com/nukeador/decky-direct-updater/releases/latest) · [Testing and troubleshooting](docs/steam-deck-testing.md) · [Development](docs/development.md)

Independent community project, not affiliated with Decky Loader. [MIT license](LICENSE).
