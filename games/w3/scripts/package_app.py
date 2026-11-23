#!/usr/bin/env python3
"""Build The Witcher 3.app: a launcher shell over the external work folder.

The game's data is ~20 GB and still changing (bringup), so the app does not copy it in. Info.plist records
MNGWorkFolder; app/launcher.c reads it, chdirs there and starts build/w3-native. Only the launcher is signed.

    python3 games/w3/scripts/package_app.py --work <work> --output "/Applications/The Witcher 3.app"
             [--icon <AppIcon.icns>] [--record-work <work>]
"""
import argparse
import os
from pathlib import Path
import sys

GAME = Path(__file__).resolve().parents[1]
REPO = GAME.parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))
from tools.port_app import bundle  # noqa: E402

BUNDLE_ID = 'org.macnativegames.w3'
EXECUTABLE = 'W3'
NAME = DISPLAY_NAME = 'The Witcher 3'
VERSION = '4.04b'


def require(condition, message):
    if not condition:
        raise ValueError(message)


def verify(work):
    runtime = work / 'build/w3-native'
    require(runtime.is_file() and os.access(runtime, os.X_OK), f'no runtime: run make runtime ({runtime})')
    modules = work / 'rewritten/local'
    for name in ('main.patched.bin', 'sdk.patched.bin'):
        require((modules / name).is_file(), f'missing game module: {modules / name} (run make prepare)')
    require((work / 'extracted/local/romfs/runtime-index.bin').is_file(), 'RomFS index missing (run make prepare)')
    return runtime


def package(work, output, icon=None, record=None):
    work, output = work.resolve(), output.resolve()
    require(output.suffix == '.app', '--output must end in .app')
    require(work != output and work not in output.parents and output not in work.parents,
            'the app and the work folder must be separate')
    verify(work)
    if icon is None and (work / 'build/AppIcon.icns').is_file():
        icon = work / 'build/AppIcon.icns'
    with bundle.staged(output) as stage:
        assemble(stage, work, icon, record)
    bundle.register(output)
    print(f'Packaged: {output}')
    return output


def assemble(stage, work, icon, record):
    contents, macos, resources = stage / 'Contents', stage / 'Contents/MacOS', stage / 'Contents/Resources'
    macos.mkdir(parents=True)
    bundle.compile_launcher(GAME / 'app/launcher.c', macos / EXECUTABLE, frameworks=('CoreFoundation',))
    icon_file = bundle.icon(icon, resources, 'AppIcon')
    info = bundle.bundle_info(executable=EXECUTABLE, bundle_id=BUNDLE_ID, name=NAME, display_name=DISPLAY_NAME,
                              version=VERSION, build='1', minimum_system=bundle.deployment_target(), icon_file=icon_file)
    commit = bundle.source_commit(REPO)
    work_record = {'MNGWorkFolder': str(work), 'MNGSourceRepo': str(REPO),
                   **({'MNGSourceCommit': commit} if commit else {})}
    bundle.write_info(stage, {**info, **work_record, **(record or {})})
    bundle.sign(stage, BUNDLE_ID, deep=False)
    bundle.verify_signature(stage)
    bundle.check_launcher(macos / EXECUTABLE)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--work', type=Path, required=True)
    ap.add_argument('--output', type=Path, required=True)
    ap.add_argument('--icon', type=Path)
    ap.add_argument('--record-work', type=Path)
    args = ap.parse_args()
    try:
        package(args.work, args.output, args.icon)
    except (OSError, ValueError, Exception) as error:
        print(f'ERROR: packaging failed: {error}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
