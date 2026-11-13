"""Pure Java save-file policy tests. Portable: no SDK, PT or credentials."""
import os
import pathlib
import shutil
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]


@unittest.skipUnless(shutil.which('javac') and shutil.which('java')
                     and not os.environ.get('PT_MCP_PYTHON_ONLY'),
                     'JDK unavailable or explicitly Python-only')
class SaveFilePolicyTests(unittest.TestCase):
    def test_policy(self):
        with tempfile.TemporaryDirectory() as out:
            folder = ROOT / 'backend/java/src/main/java/com/ptmcp'
            subprocess.run(['javac', '-d', out,
                            str(folder / 'SaveFilePolicy.java'),
                            str(ROOT / 'tests/java/SaveFilePolicyTest.java')], check=True)
            subprocess.run(['java', '-ea', '-cp', out, 'com.ptmcp.SaveFilePolicyTest'],
                           check=True, timeout=15)


if __name__ == '__main__':
    unittest.main()
