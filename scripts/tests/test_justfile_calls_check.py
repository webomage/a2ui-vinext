#!/usr/bin/env python3
"""Red probes for justfile_calls_check.py (T431 run 7).

The load-bearing case is the exact line that shipped: a root recipe body calling a recipe that only
another justfile defines, behind a `-` prefix that made its failure invisible. The rest pin the
skips — delegation, `cd … &&`, comments, quoted prose — because a check that fires on English gets
switched off, and one that fires on legitimate delegation is wrong.
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "justfile_calls_check.py"


def run(body: str) -> subprocess.CompletedProcess:
    d = Path(tempfile.mkdtemp(prefix="jcc-"))
    (d / "justfile").write_text(body)
    return subprocess.run([sys.executable, str(SCRIPT), "--justfile", str(d / "justfile")],
                          capture_output=True, text=True)


class JustfileCallsCheck(unittest.TestCase):

    def test_the_shipped_bug_fails(self):
        r = run("present:\n    @echo ok\n\n_post-deploy-knowledge:\n    -@just knowledge-light\n")
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertIn("`just knowledge-light` — no such recipe", r.stdout)

    def test_a_defined_target_passes(self):
        r = run("a:\n    @echo a\n\nb:\n    -@just a\n")
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn("1 bare `just` call(s)", r.stdout)

    def test_delegation_is_not_a_call_into_this_justfile(self):
        r = run("a:\n    @just --justfile other/justfile missing\n"
                "b:\n    @just -f other/justfile missing\n"
                "c:\n    @cd other && just missing\n")
        self.assertEqual(r.returncode, 0, r.stdout)

    def test_comments_and_quoted_prose_are_not_calls(self):
        r = run("a:\n    # this fails just like a real absence\n"
                "    @echo \"  just do <recipe>   run a recipe\"\n")
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn("0 bare `just` call(s)", r.stdout)

    def test_shebang_recipes_are_scanned(self):
        r = run("a:\n    #!/usr/bin/env bash\n    set -euo pipefail\n    exec just nope\n")
        self.assertEqual(r.returncode, 1, r.stdout)

    def test_unreadable_justfile_is_unmeasured_not_clean(self):
        r = run("this is not a justfile ::: {{\n")
        self.assertEqual(r.returncode, 2, r.stdout)
        self.assertIn("cannot measure", r.stdout)


if __name__ == "__main__":
    unittest.main()
