# Loaded by Python when this folder is on PYTHONPATH (release.yml, Intel Mac job, pip steps only): pip then picks
# wheels for the macOS version in PIP_MACOS_VERSION (the oldest one the app supports) instead of the runner's newer
# macOS, whose numpy/scipy builds need macOS 14.
import os
import platform

_target = os.environ.get("PIP_MACOS_VERSION")
if _target:
    _real_mac_ver = platform.mac_ver

    def _mac_ver(*args, **kwargs):
        release, versioninfo, machine = _real_mac_ver(*args, **kwargs)
        return _target, versioninfo, machine

    platform.mac_ver = _mac_ver
