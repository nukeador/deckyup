"""Decky RPC entry points. Blocking I/O always runs off the event loop."""

import asyncio
import sys
from pathlib import Path

import decky

sys.path.insert(0, str(Path(__file__).resolve().parent))

from direct_updater.plugin_updates import Updater  # noqa: E402


class Plugin:
    async def _main(self):
        self.updater = None
        self.initialization_error = None
        try:
            plugin_directory = Path(decky.DECKY_PLUGIN_DIR)
            if not plugin_directory.is_absolute():
                raise ValueError("Decky plugin directory is unavailable")
            if not decky.DECKY_PLUGIN_SETTINGS_DIR or not decky.DECKY_PLUGIN_RUNTIME_DIR:
                raise ValueError("Decky persistent directories are unavailable")
            self.updater = await asyncio.to_thread(
                Updater,
                plugin_directory.parent,
                decky.DECKY_PLUGIN_SETTINGS_DIR,
                decky.DECKY_PLUGIN_RUNTIME_DIR,
            )
        except (ValueError, OSError, ImportError) as error:
            self.initialization_error = str(error)
            decky.logger.error("Updater initialization failed: %s", error)

    def _ready(self):
        if not getattr(self, "updater", None):
            raise ValueError(
                getattr(self, "initialization_error", None) or "Updater is starting; retry shortly"
            )
        return self.updater

    async def list_plugins(self):
        return await asyncio.to_thread(self._ready().list_plugins)

    async def check_updates(self, refresh=False):
        loop = asyncio.get_running_loop()
        emit = getattr(decky, "emit", None)

        def progress(plugin):
            if emit:
                asyncio.run_coroutine_threadsafe(emit("update_result", plugin), loop)

        return await asyncio.to_thread(self._ready().check, bool(refresh), progress)

    async def search_source(self, identifier):
        try:
            candidates = await asyncio.to_thread(self._ready().search, identifier)
            return {"candidates": candidates, "error": None}
        except (ValueError, OSError, ImportError) as error:
            return {"candidates": [], "error": str(error)}

    async def verify_source(self, identifier, source):
        try:
            candidates = await asyncio.to_thread(self._ready().verify_source, identifier, source)
            return {"candidates": candidates, "error": None}
        except (ValueError, OSError, ImportError) as error:
            return {"candidates": [], "error": str(error)}

    async def confirm_source(self, identifier, source):
        try:
            await asyncio.to_thread(self._ready().confirm, identifier, source)
            return {"success": True, "error": None}
        except (ValueError, OSError, ImportError) as error:
            return {"success": False, "error": str(error)}

    async def list_releases(self, identifier, cursor=None):
        try:
            page = await asyncio.to_thread(self._ready().list_releases, identifier, cursor)
            return {**page, "error": None}
        except (ValueError, OSError, ImportError) as error:
            return {"releases": [], "next_cursor": None, "error": str(error)}

    async def stage_release(self, identifier, release_id, asset_id, confirm_downgrade=False):
        try:
            update = await asyncio.to_thread(
                self._ready().stage_release, identifier, release_id, asset_id, confirm_downgrade
            )
            return {"update": update, "error": None}
        except (ValueError, OSError, ImportError) as error:
            return {"update": None, "error": str(error)}

    async def stage_update(self, identifier, release_id, asset_id):
        try:
            update = await asyncio.to_thread(self._ready().stage, identifier, release_id, asset_id)
            return {"update": update, "error": None}
        except (ValueError, OSError, ImportError) as error:
            return {"update": None, "error": str(error)}

    async def _unload(self):
        pass
