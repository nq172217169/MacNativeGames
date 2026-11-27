"""Kirby's two-player Npad routing, without game files or physical controllers."""
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

GAME = Path(__file__).resolve().parents[1]
PROBE = GAME / "tests/two_player/probe.m"
OBJC = ["-fobjc-arc", "-framework", "Foundation", "-framework", "GameController"]


@unittest.skipUnless(sys.platform == "darwin" and shutil.which("xcrun"), "needs macOS and the Xcode command line tools")
class TwoPlayerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="kirby-two-player-")
        cls.probe = Path(cls.temp.name) / "probe"
        build = subprocess.run(
            ["xcrun", "clang", "-std=gnu11", "-O1", "-Wall", "-Wextra", "-Wno-unused-function",
             "-Wno-unused-parameter", "-I" + str(GAME / "runtime"), str(PROBE), *OBJC,
             "-o", str(cls.probe)],
            capture_output=True, text=True, timeout=180,
        )
        if build.returncode:
            cls.temp.cleanup()
            raise AssertionError(build.stderr[-4000:])

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def run_probe(self, fallback=False):
        env = {k: v for k, v in os.environ.items() if k != "TOTK_TWO_PLAYERS"}
        if fallback:
            env["TOTK_TWO_PLAYERS"] = "0"
        args = [str(self.probe)] + (["fallback"] if fallback else [])
        result = subprocess.run(args, env=env, capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("pass:", result.stdout)

    def test_second_controller_is_player_two(self):
        self.run_probe()

    def test_two_players_can_be_disabled(self):
        self.run_probe(fallback=True)


if __name__ == "__main__":
    unittest.main()
