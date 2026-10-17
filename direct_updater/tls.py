"""Verified HTTPS for both system Python and Decky's frozen Python runtime."""

import ssl


def github_ssl_context():
    context = ssl.create_default_context()
    # Decky's bundled OpenSSL may point at /usr/lib/ssl, absent on SteamOS.
    # Decky ships certifi for the same reason; retain system trust and add its CAs.
    try:
        import certifi
    except ImportError:
        certifi = None
    if certifi is not None:
        context.load_verify_locations(cafile=certifi.where())
    return context
