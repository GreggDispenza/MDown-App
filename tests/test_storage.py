"""Tests for mobile save-location selection (mdown_app.storage).

Pure logic, no Flet — safe for the Android dependency-set CI job too.
"""

from mdown_app.storage import pick_mobile_save_dir


def test_prefers_external_dir_when_present():
    internal = "/data/data/app.mdown.mdown/files"
    seen = {}

    def isdir(p):
        seen["probed"] = p
        return True

    path, reachable = pick_mobile_save_dir(internal, isdir=isdir)
    assert path == "/storage/emulated/0/Android/data/app.mdown.mdown/files"
    assert reachable is True
    assert seen["probed"] == path  # it probed the external dir, not internal


def test_multi_user_internal_path_extracts_package():
    internal = "/data/user/0/app.mdown.mdown/app_flet/storage/data"
    path, reachable = pick_mobile_save_dir(internal, isdir=lambda p: True)
    assert path == "/storage/emulated/0/Android/data/app.mdown.mdown/files"
    assert reachable is True


def test_falls_back_to_internal_when_external_missing():
    internal = "/data/data/app.mdown.mdown/files"
    path, reachable = pick_mobile_save_dir(internal, isdir=lambda p: False)
    assert path == internal
    assert reachable is False


def test_non_android_path_is_never_reachable():
    # Desktop home dir (the code's own fallback) has no package to derive.
    internal = "/home/someone"
    path, reachable = pick_mobile_save_dir(internal, isdir=lambda p: True)
    assert path == internal
    assert reachable is False


def test_empty_input_is_safe():
    path, reachable = pick_mobile_save_dir("", isdir=lambda p: True)
    assert path == ""
    assert reachable is False
