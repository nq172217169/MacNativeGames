#!/usr/bin/env python3
"""Put a prepared work folder into The Witcher 3.app (app/launcher.c says the layout).

The app is self-contained like the other ports: runtime, rewritten modules and the RomFS image/index are APFS clones of
the work folder's (no second copy on the same volume), so Finder and Storage report the game's real size. The player's
saves/cache stay in ~/Library/Application Support/MacNativeGames/W3, outside the app. Assembled beside the output and
replacing it only when complete, then signed ad hoc with its bundle ID as the designated requirement and asked --check.

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
ROMFS_FILES = ('index.json', 'runtime-index.bin', 'romfs.bin')


def require(condition, message):
    if not condition:
        raise ValueError(message)


def verify(work):
    """What the app carries, checked: {name: path}."""
    files = {'runtime': work / 'build/w3-native'}
    require(files['runtime'].is_file() and os.access(files['runtime'], os.X_OK),
            f'no runtime: run make runtime ({files["runtime"]})')
    modules = work / 'rewritten/local'
    for name in ('main.patched.bin', 'sdk.patched.bin'):
        require((modules / name).is_file(), f'missing game module: {modules / name} (run make prepare)')
    files['modules'] = modules
    romfs = work / 'extracted/local/romfs'
    for name in ROMFS_FILES:
        require((romfs / name).is_file(), f'RomFS {name} missing: {romfs} (run make prepare)')
    require((romfs / 'romfs.bin').stat().st_size > 1 << 30, f'RomFS image too small: {romfs / "romfs.bin"}')
    files['romfs'] = romfs
    return files


def package(work, output, icon=None, record=None):
    work, output = work.resolve(), output.resolve()
    require(output.suffix == '.app', '--output must end in .app')
    require(work != output and work not in output.parents and output not in work.parents,
            'the app and the work folder must be separate')
    files = verify(work)
    if icon is None and (work / 'build/AppIcon.icns').is_file():
        icon = work / 'build/AppIcon.icns'
    with bundle.staged(output) as stage:   # assembled beside the output, which it replaces only when complete
        assemble(stage, files, icon, record)
    bundle.register(output)
    print(f'Packaged: {output}')
    return output


def assemble(stage, files, icon, record):
    """The bundle at stage, signed, verified and asked --check."""
    contents, macos = stage / 'Contents', stage / 'Contents/MacOS'
    game = contents / 'Resources/game'
    macos.mkdir(parents=True)
    bundle.clone_file(files['runtime'], game / 'build/w3-native')
    bundle.clone_tree(files['modules'], game / 'rewritten/local')
    for name in ROMFS_FILES:
        bundle.clone_file(files['romfs'] / name, game / 'extracted/local/romfs' / name)
    bundle.compile_launcher(GAME / 'app/launcher.c', macos / EXECUTABLE)
    icon_file = bundle.icon(icon, contents / 'Resources', 'AppIcon')
    info = bundle.bundle_info(executable=EXECUTABLE, bundle_id=BUNDLE_ID, name=NAME, display_name=DISPLAY_NAME,
                              version=VERSION, build='1', minimum_system=bundle.deployment_target(), icon_file=icon_file)
    commit = bundle.source_commit(REPO)
    bundle.write_info(stage, {**info, **({'MNGSourceCommit': commit} if commit else {}), **(record or {})})
    bundle.sign(stage, BUNDLE_ID, deep=False)
    bundle.verify_signature(stage)
    bundle.check_launcher(macos / EXECUTABLE)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--work', type=Path, required=True)
    ap.add_argument('--output', type=Path, required=True)
    ap.add_argument('--icon', type=Path)
    ap.add_argument('--record-work', type=Path, help='recorded in Info.plist (an update reuses this work folder)')
    args = ap.parse_args()
    try:
        package(args.work, args.output, args.icon)
    except (OSError, ValueError, Exception) as error:
        print(f'ERROR: packaging failed: {error}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
