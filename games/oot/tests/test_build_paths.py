"""#2045: a work folder whose path has spaces (the default sits next to the dump, named after the game) still builds the
runtime; #2055: the app records what the Update page needs (the checkout, the work folder, the Python, the commit)."""
import re
import importlib.util
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock

GAME = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('oot_build_paths', GAME / 'build.py')
build = importlib.util.module_from_spec(spec); spec.loader.exec_module(build)


class WorkPathTests(unittest.TestCase):
    def test_a_path_with_spaces_gets_an_alias_without_them(self):
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp) / 'The Legend of Zelda Ocarina of Time [NUP]' / 'OcarinaOfTime_build'; work.mkdir(parents=True)
            alias = build.make_path(work, 'oot')   # tools/port_app/make_path.py since issue #2284
            self.assertNotIn(' ', str(alias))
            self.assertEqual(alias.resolve(), work.resolve())
            self.assertEqual(build.make_path(work, 'oot'), alias)   # the same alias each time
            plain = Path(tmp) / 'plain'; plain.mkdir()
            self.assertEqual(build.make_path(plain, 'oot'), plain)

    def test_make_refuses_a_work_path_with_spaces_and_says_why(self):
        result = subprocess.run(['make', '-n', '-C', str(GAME), 'WORK=/tmp/a b'], capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('WORK must not contain spaces', result.stdout + result.stderr)

    def test_both_runtime_builds_use_the_alias(self):
        source = (GAME / 'build.py').read_text()
        self.assertEqual(source.count("'WORK='+str(make_path(work,'oot'))"), 2)
        self.assertNotIn("'WORK='+str(work)", source)


class AppRunningTests(unittest.TestCase):
    """#1784 (Ocarina of Time, after 577e4576 fixed the other apps): the Update window runs the game's executable with
    --update-install <pid> or --update-check and waits for the installer, so the installer must not wait for it."""
    APP = Path('/Apps/Ocarina of Time.app')

    def running(self, *commands):
        exe = str((self.APP / 'Contents/MacOS/OcarinaOfTime').resolve())
        table = '\n'.join(f'{100 + i} {exe}' for i in range(len(commands)))
        args = {str(100 + i): f'{exe} {c}'.rstrip() for i, c in enumerate(commands)}
        def fake(cmd, **kw):
            out = table if cmd[:3] == ['ps', '-axo', 'pid=,comm='] else args[cmd[cmd.index('-p') + 1]]
            return subprocess.CompletedProcess(cmd, 0, out, '')
        from unittest import mock
        with mock.patch.object(build.subprocess, 'run', fake):
            return build.app_running(self.APP)

    def test_the_update_window_is_not_the_game(self):
        self.assertFalse(self.running('--update-install 4242'))
        self.assertFalse(self.running('--update-check'))

    def test_the_game_is_running(self):
        self.assertTrue(self.running(''))
        self.assertTrue(self.running('--update-check', ''))
        self.assertTrue(self.running('--update-install x'))   # not the helper's form: treated as the game


class WaitUntilGameClosedTests(unittest.TestCase):
    """2026-11-24: an express update waited for a player's open game for ever. The wait must guide the player,
    keep waiting while they close it, and cancel itself after a timeout — never end the game for them."""

    def run_wait(self, running_states, timeout=300, ticks=()):
        """Drive app_running() through running_states (one bool per call); time via ticks (monotonic values)."""
        calls = iter(running_states)
        times = iter(ticks)
        out = []
        with mock.patch.object(build, 'app_running', side_effect=lambda app: next(calls)), \
             mock.patch.object(build.time, 'monotonic', side_effect=lambda: next(times)), \
             mock.patch.object(build.time, 'sleep'), \
             mock.patch('builtins.print', side_effect=lambda *a, **k: out.append(' '.join(map(str, a)))):
            return build.wait_until_game_closed(Path('/Apps/Ocarina of Time.app'), timeout=timeout), out

    def test_game_closed_returns_without_prompt(self):
        waited, out = self.run_wait([False], ticks=(0.0, 0.0))
        self.assertEqual(waited, 0.0)
        self.assertEqual(out, [])

    def test_waits_then_continues_when_player_closes_it(self):
        # running, running, then closed; monotonic: start, first loop, second check after sleep
        waited, out = self.run_wait([True, True, False], ticks=(0.0, 1.0, 3.0, 3.0))
        self.assertEqual(len(out), 1)
        self.assertIn('游戏仍在运行', out[0])
        self.assertIn('close it', out[0])

    def test_times_out_and_cancels_without_ending_the_game(self):
        with self.assertRaises(TimeoutError) as ctx:
            self.run_wait([True], timeout=10, ticks=(0.0, 11.0))
        self.assertIn('游戏在 10 秒后仍未关闭', str(ctx.exception))
        self.assertIn('update cancelled', str(ctx.exception))

    def test_no_limit_timeout_never_raises(self):
        # timeout 0 disables the guard; the game closing still ends the wait
        waited, _ = self.run_wait([True, True, False], timeout=0, ticks=(0.0, 1.0, 3.0, 3.0))
        self.assertEqual(waited, 3.0)

    def test_reminds_every_minute(self):
        # running for >120 s: first notice plus a 60 s reminder
        waited, out = self.run_wait([True, True, True, False], timeout=300,
                                    ticks=(0.0, 1.0, 61.0, 63.0, 63.0))
        self.assertEqual(len(out), 2)
        self.assertIn('剩余约', out[1])


class ToolCheckTests(unittest.TestCase):
    """#2070 (the reporter's M5 build): without ffmpeg the build ran for minutes and stopped at the opening overlay. Since
    fa394da8 (2026-11-12) the overlay cuts its clip in Python (scripts/webm_one_frame.py, the same bytes as ffmpeg's
    remux), so there is no tool to check: the build and the overlay must not run ffmpeg or ffprobe again."""
    RUNS_FFMPEG = re.compile(r"""['"](ffmpeg|ffprobe)['"]""")

    def test_the_build_and_the_opening_overlay_run_no_ffmpeg(self):
        for name in ('build.py', 'scripts/make_opening_overlay.py', 'scripts/webm_one_frame.py'):
            with self.subTest(name=name):
                self.assertIsNone(self.RUNS_FFMPEG.search((GAME / name).read_text()))

    def test_the_opening_overlay_cuts_its_clip_in_python(self):
        overlay = (GAME / 'scripts/make_opening_overlay.py').read_text()
        self.assertIn('import webm_one_frame', overlay)
        self.assertIn('webm_one_frame.one_frame(', overlay)


class UpdateInfoTests(unittest.TestCase):
    def test_the_app_records_its_checkout_work_folder_python_and_commit(self):
        source = (GAME / 'build.py').read_text()
        self.assertIn('build_app.record_update_source(info,work)', source)
        self.assertIn("info['MNGSourceCommit']=commit", source)


if __name__ == '__main__':
    unittest.main()
