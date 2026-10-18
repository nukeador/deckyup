"""Manifest facts and deterministic review policy, not code or malware analysis."""

import re
from urllib.parse import urlsplit

INVALID_SECURITY = "Could not inspect package access. Installation stopped."
CHANGED_SECURITY = "Prepared package or installed plugin changed. Prepare it again."
ACK_REQUIRED = "Review plugin access before continuing."


def security_facts(manifest, package, backend):
    flags = manifest.get("flags", [])
    binaries = package.get("remote_binary", [])
    if (
        not isinstance(flags, list)
        or len(flags) > 100
        or any(not isinstance(flag, str) or len(flag) > 160 for flag in flags)
        or not isinstance(binaries, list)
        or len(binaries) > 100
    ):
        raise ValueError(INVALID_SECURITY)
    downloads = []
    names = set()
    for binary in binaries:
        if not isinstance(binary, dict):
            raise ValueError(INVALID_SECURITY)
        name, url, digest = (binary.get(key) for key in ("name", "url", "sha256hash"))
        if (
            not isinstance(name, str)
            or not name
            or len(name) > 160
            or name in (".", "..")
            or any(c in name for c in "/\\\0\r\n")
            or name in names
            or not isinstance(url, str)
            or len(url) > 8192
            or any(ord(c) < 33 for c in url)
            or (
                digest is not None
                and (not isinstance(digest, str) or not re.fullmatch(r"[a-fA-F0-9]{64}", digest))
            )
        ):
            raise ValueError(INVALID_SECURITY)
        try:
            parsed = urlsplit(url)
            host = parsed.hostname
            if (
                parsed.scheme not in {"https", "http"}
                or not host
                or parsed.username
                or parsed.password
            ):
                raise ValueError(INVALID_SECURITY)
            # Validate the port too. Only domains are exposed to the frontend.
            parsed.port
            host = host.encode("idna").decode("ascii").lower().rstrip(".")
        except (ValueError, UnicodeError) as error:
            raise ValueError(INVALID_SECURITY) from error
        names.add(name)
        downloads.append(
            {"name": name, "source_host": host, "declared_hash": digest, "source_url": url}
        )
    return {
        "root_requested": "root" in flags,
        "flags": flags,
        "has_python_backend": backend,
        "external_binaries": downloads,
    }


def public_facts(facts):
    if facts is None:
        return None
    return {
        **facts,
        "external_binaries": [
            {key: value for key, value in binary.items() if key != "source_url"}
            for binary in facts["external_binaries"]
        ],
    }


def assess_security(current, previous=None, updating=False):
    findings = []
    old_root = previous["root_requested"] if previous is not None else None
    old_binaries = (
        {item["name"]: item for item in previous["external_binaries"]}
        if previous is not None
        else {}
    )
    added = [
        item["name"] for item in current["external_binaries"] if item["name"] not in old_binaries
    ]
    changed = [
        item["name"]
        for item in current["external_binaries"]
        if item["name"] in old_binaries
        and item["source_host"] != old_binaries[item["name"]]["source_host"]
    ]

    def finding(kind, warning=True):
        findings.append({"kind": kind, "severity": "warning" if warning else "information"})

    if current["root_requested"]:
        finding(
            "root_added" if updating and old_root is False else "root_requested",
            old_root is not True,
        )
    if current["external_binaries"]:
        if not updating or previous is None:
            finding("external_binaries")
        else:
            if added:
                finding("external_binaries_added")
            if changed:
                finding("external_binary_origin_changed")
    if updating and previous is None:
        # Unknown is not equivalent to a known no-root installation.
        finding(
            "comparison_unavailable",
            current["root_requested"] or bool(current["external_binaries"]),
        )
    return {
        **public_facts(current),
        "previous_root_requested": old_root,
        "previous_has_python_backend": previous["has_python_backend"]
        if previous is not None
        else None,
        "previous_external_binaries": public_facts(previous)["external_binaries"]
        if previous is not None
        else None,
        "added_binary_names": added,
        "changed_binary_source_hosts": changed,
        "comparison_available": previous is not None,
        "updating": updating,
        "findings": findings,
        "requires_acknowledgment": any(item["severity"] == "warning" for item in findings),
    }
