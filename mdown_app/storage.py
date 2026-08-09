"""Where to save a converted file on mobile — and whether the user can reach it.

This is deliberately free of any Flet import so it can be unit-tested (and
imported by the Android dependency-set CI job, which doesn't install Flet).

The problem it solves: on Android, Flet hands the app only its *internal*
storage dir (``FLET_APP_STORAGE_DATA`` → ``/data/data/<pkg>/...``), which no
file manager can open. Flet 0.28.3's ``FilePicker.save_file`` takes no ``bytes``
argument, so it can't write through the Storage Access Framework on mobile
either. The best permission-free, user-reachable location we can target from
pure Python is the app's *external* files dir
(``/storage/emulated/0/Android/data/<pkg>/files``), which the system Files app
exposes. We prefer it when it exists and fall back to internal storage — telling
the caller which case applies so the UI can be honest about reachability.
"""

from __future__ import annotations

import os
import re
from typing import Callable, Tuple

# The internal path Flet reports looks like /data/data/<pkg>/... or, on
# multi-user devices, /data/user/<n>/<pkg>/... — capture the package id.
_INTERNAL_PKG_RE = re.compile(r"/data/(?:data|user/\d+)/([A-Za-z0-9_.]+)(?:/|$)")

# Primary external storage root on Android. Its own-app subtree is always
# writable by the app without any permission.
_EXTERNAL_ROOT = "/storage/emulated/0"


def pick_mobile_save_dir(
    internal_dir: str,
    isdir: Callable[[str], bool] = os.path.isdir,
) -> Tuple[str, bool]:
    """Choose a directory to save into on mobile and report reachability.

    Prefers the app's external files dir (reachable from a file manager, no
    permission required) when it exists; otherwise returns ``internal_dir``.

    Returns ``(directory, reachable)`` where ``reachable`` is True only for the
    external location a user can actually open.
    """
    match = _INTERNAL_PKG_RE.search(internal_dir or "")
    if match:
        external = f"{_EXTERNAL_ROOT}/Android/data/{match.group(1)}/files"
        if isdir(external):
            return external, True
    return internal_dir, False
