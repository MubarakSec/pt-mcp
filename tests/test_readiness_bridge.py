import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import Mock
from live_bridge import LiveBridge, LiveBridgeError

ROOT=Path(__file__).resolve().parents[1]

class ReadinessBridgeTests(unittest.TestCase):
    def test_status_is_passive_and_never_infers_authentication_from_process(self):
        bridge=LiveBridge(command=['absent'],cwd=ROOT)
        bridge._start=Mock(side_effect=AssertionError('passive status started process'))
        self.assertEqual(bridge.status()['ipc_authentication'],'unknown')
        bridge._proc=Mock();bridge._proc.poll.return_value=None
        self.assertTrue(bridge.status()['child_alive'])
        self.assertEqual(bridge.status()['ipc_authentication'],'unknown')
        bridge._start.assert_not_called()
        bridge._proc=None

    def test_probe_is_sent_once_and_cached_as_historical_evidence_only(self):
        bridge=LiveBridge(command=['absent'],cwd=ROOT)
        bridge._start=Mock()
        reply={'structuredContent':{'status':'pass','reason':'authenticated_live_read','observed_at':'synthetic',
                                    'evidence':{'authenticated':True}},'content':[]}
        bridge._request=Mock(return_value=reply)
        self.assertEqual(bridge.call_tool('pt_live_probe_connection',{'timeout_ms':1000}),reply)
        bridge._request.assert_called_once_with('tools/call',{'name':'pt_probe_connection','arguments':{'timeout_ms':1000}})
        self.assertEqual(bridge.status()['last_connection_probe']['status'],'pass')
        self.assertEqual(bridge.status()['ipc_authentication'],'unknown')

    def test_unavailable_backend_reports_unknown_and_offline_tools_survive(self):
        requests=[('initialize',{}),('tools/call',{'name':'pt_live_probe_connection','arguments':{'timeout_ms':50}}),
                  ('tools/call',{'name':'pt_live_get_readiness','arguments':{'devices':['R']}}),
                  ('tools/call',{'name':'pt_live_validate_network','arguments':{'checks':[{'kind':'boot','device':'R'}]}}),
                  ('tools/list',{})]
        env=dict(os.environ,PT_MCP_LIVE_COMMAND=json.dumps(['/no/pt-mcp-backend']))
        wire=''.join(json.dumps({'id':i,'jsonrpc':'2.0','method':m,'params':p})+'\n' for i,(m,p) in enumerate(requests))
        p=subprocess.run([sys.executable,str(ROOT/'server.py')],input=wire,text=True,capture_output=True,env=env,timeout=10)
        self.assertEqual(p.returncode,0,p.stderr)
        replies=[json.loads(line) for line in p.stdout.splitlines()]
        for reply in replies[1:4]:
            self.assertEqual(reply['result']['structuredContent']['status'],'unknown')
        names={t['name'] for t in replies[-1]['result']['tools']}
        self.assertIn('pt_open',names);self.assertIn('pt_live_validate_network',names)

    def test_diagnostic_deadline_covers_child_initialization(self):
        with tempfile.TemporaryDirectory() as tmp:
            child=Path(tmp)/'stall.py'
            child.write_text('import sys,time\nfor line in sys.stdin:\n time.sleep(10)\n')
            bridge=LiveBridge(command=[sys.executable,str(child)],cwd=ROOT,timeout=45)
            started=time.monotonic()
            try:
                with self.assertRaises(LiveBridgeError):
                    bridge.call_tool('pt_live_probe_connection',{'timeout_ms':20})
                self.assertLess(time.monotonic()-started,4)
                self.assertIsNone(bridge._request_deadline)
            finally:
                bridge.close()

    def test_invalid_deadline_never_launches_backend(self):
        bridge=LiveBridge(command=['absent'],cwd=ROOT)
        bridge._start=Mock()
        for value in (False,0,30001,1.5,'1000'):
            with self.assertRaises(ValueError): bridge.call_tool('pt_live_probe_connection',{'timeout_ms':value})
        bridge._start.assert_not_called()
