"""Atomic persistent source associations and HTTP cache."""

import json
import os
import tempfile
import threading
from pathlib import Path


class State:
    def __init__(self, directory):
        self.path = Path(directory) / "state.json"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        try:
            self.data = json.loads(self.path.read_text())
            if not isinstance(self.data, dict):
                raise ValueError("Invalid state")
        except FileNotFoundError:
            self.data = {}
        except (ValueError, OSError):
            # Preserve malformed state for manual recovery instead of overwriting it.
            raise ValueError("Cannot read persistent state; recover state.json before continuing")
        sections = ("sources", "cache", "associations", "discovery")
        for section in sections:
            self.data.setdefault(section, {})
        if not all(isinstance(self.data[key], dict) for key in sections):
            raise ValueError("Invalid persistent state sections; recover state.json")

    def get(self, section, key):
        with self.lock:
            return self.data[section].get(key)

    def put(self, section, key, value, max_find_entries=None):
        with self.lock:
            self.data[section][key] = value
            if max_find_entries:
                entries = sorted(
                    (
                        k
                        for k, v in self.data[section].items()
                        if isinstance(v, dict) and v.get("find_cache")
                    ),
                    key=lambda k: self.data[section][k].get("time", 0),
                )
                for old in entries[:-max_find_entries]:
                    del self.data[section][old]
            descriptor, temporary = tempfile.mkstemp(dir=self.path.parent, prefix=".state-")
            try:
                with os.fdopen(descriptor, "w") as stream:
                    json.dump(self.data, stream)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(temporary, self.path)
            finally:
                if os.path.exists(temporary):
                    os.unlink(temporary)
