"""Portable bridge regression tests; pure Java policy tests run when JDK is present."""
import pathlib
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import Mock
from live_bridge import LiveBridge, LiveBridgeError

ROOT = pathlib.Path(__file__).resolve().parents[1]


class BridgeFailureTests(unittest.TestCase):
    def test_lost_reply_is_never_replayed(self):
        for message in ('request timed out', 'backend disconnected'):
            bridge = LiveBridge(command=['missing'], cwd=ROOT)
            bridge._start = Mock()
            bridge._stop_child = Mock()
            bridge._request = Mock(side_effect=LiveBridgeError(message))
            with self.assertRaisesRegex(LiveBridgeError, 'Outcome may be unknown'):
                bridge.call_tool('pt_live_run_cli_batch', {'commands': ['hostname x']})
            bridge._request.assert_called_once()
            bridge._stop_child.assert_called_once()


@unittest.skipUnless(shutil.which('javac') and shutil.which('java'), 'JDK unavailable')
class JavaPolicyTests(unittest.TestCase):
    def test_cli_policy(self):
        with tempfile.TemporaryDirectory() as out:
            subprocess.run(['javac', '-d', out,
                            str(ROOT / 'backend/java/src/main/java/com/ptmcp/CliPolicy.java'),
                            str(ROOT / 'tests/java/CliPolicyTest.java')], check=True)
            subprocess.run(['java', '-ea', '-cp', out, 'com.ptmcp.CliPolicyTest'], check=True)

    def test_presentation_policy(self):
        with tempfile.TemporaryDirectory() as out:
            subprocess.run(['javac', '-d', out,
                            str(ROOT / 'backend/java/src/main/java/com/ptmcp/PresentationPolicy.java'),
                            str(ROOT / 'tests/java/PresentationPolicyTest.java')], check=True)
            subprocess.run(['java', '-ea', '-cp', out, 'com.ptmcp.PresentationPolicyTest'], check=True)


@unittest.skipUnless(shutil.which('javac') and shutil.which('java'), 'JDK unavailable')
class JavaDiagnosticsTests(unittest.TestCase):
    def run_harness(self, name):
        with tempfile.TemporaryDirectory() as out:
            folder = ROOT / 'backend/java/src/main/java/com/ptmcp'
            files = [str(folder / (n + '.java')) for n in
                     ('CliPolicy', 'PresentationPolicy', 'DiagnosticsPolicy', 'DiagnosticExecutor', 'TerminalActivity', 'ValidationEngine')]
            subprocess.run(['javac', '-d', out, *files, str(ROOT / 'tests/java/DiagnosticsPolicyTest.java'), str(ROOT / 'tests/java' / (name + '.java'))], check=True)
            subprocess.run(['java', '-ea', '-cp', out, 'com.ptmcp.' + name], check=True, timeout=15)

    def test_diagnostics_policy(self):
        self.run_harness('DiagnosticsPolicyTest')

    def test_terminal_activity(self):
        self.run_harness('TerminalActivityTest')

    def test_validation_engine(self):
        self.run_harness('ValidationEngineTest')
