"""Harness safety/orchestration tests with synthetic tool replies, never live evidence."""
import contextlib
import copy
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock,patch
from scripts.pt_integration import Harness,IntegrationError,main,presentation,MUTATIONS
from live_bridge import LiveBridgeError

ROOT=Path(__file__).resolve().parents[1]
CANVAS={'devices':[{'name':'synthetic','x':10,'y':20,'type':'pc','model':'PC-PT'}], 'links':[],
        'notes':[{'id':'synthetic-note','text':'العربية','x':0,'y':0}]}


class FakeTools:
    def __init__(self,canvas=None):
        self.canvas=copy.deepcopy(canvas if canvas is not None else CANVAS);self.calls=[]
    def call_tool(self,name,args):
        self.calls.append((name,args))
        if name=='pt_live_probe_connection':data={'status':'pass'}
        elif name=='pt_live_get_canvas':data=copy.deepcopy(self.canvas)
        elif name=='pt_live_save_file':
            Path(args['path']).write_bytes(b'synthetic orchestration fixture; NOT a Packet Tracer project')
            data={'saved':True}
        else:data={'outcome':'success'}
        return {'structuredContent':data,'isError':False}


class HarnessTests(unittest.TestCase):
    def test_nonempty_project_prevents_every_mutation(self):
        client=FakeTools();h=Harness(client,'/unused')
        with self.assertRaises(IntegrationError):h.preflight()
        self.assertFalse(h.cleared_workspace)
        self.assertFalse(any(name in MUTATIONS for name,args in client.calls))

    def test_incomplete_canvas_is_never_treated_as_empty(self):
        client=FakeTools({});h=Harness(client,'/unused')
        with self.assertRaises(IntegrationError):h.preflight()
        self.assertFalse(h.cleared_workspace)

    def test_unknown_mutation_is_dispatched_once_without_rollback(self):
        client=Mock();client.call_tool.side_effect=LiveBridgeError('reply lost')
        h=Harness(client,'/unused');h.cleared_workspace=True
        with self.assertRaises(IntegrationError) as raised:h.call('pt_live_add_device',{'name':'synthetic'})
        self.assertEqual(raised.exception.status,'unknown')
        client.call_tool.assert_called_once()

    def test_mutation_requires_successful_empty_workspace_preflight(self):
        client=FakeTools();h=Harness(client,'/unused')
        with self.assertRaises(IntegrationError):h.call('pt_live_add_device',{})
        self.assertEqual(client.calls,[])

    def test_save_requires_separate_opt_in_and_new_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            client=FakeTools();h=Harness(client,tmp);h.cleared_workspace=True
            with self.assertRaises(IntegrationError):h.save_reopen()
            self.assertEqual(client.calls,[])
            h.allow_save=True;(Path(tmp)/'scratch.pkt').write_text('keep')
            with self.assertRaises(IntegrationError):h.save_reopen()
            self.assertEqual((Path(tmp)/'scratch.pkt').read_text(),'keep')
            self.assertEqual(client.calls,[])

    def test_save_reopen_calls_once_and_compares_observed_canvas(self):
        with tempfile.TemporaryDirectory() as tmp:
            client=FakeTools();h=Harness(client,tmp,save_reopen=True);h.cleared_workspace=True
            h.wait_boot=Mock();h.validate=Mock()
            h.save_reopen()
            names=[name for name,args in client.calls]
            self.assertEqual(names.count('pt_live_save_file'),1)
            self.assertEqual(names.count('pt_live_open_file'),1)
            self.assertEqual(names.count('pt_live_run_cli'),3) # explicitly requested startup saves
            self.assertTrue((Path(tmp)/'scratch.pkt').exists())
            self.assertEqual(h.report['save_reopen'],'pass')
            h.wait_boot.assert_called_once();h.validate.assert_called_once()

    def test_persistence_comparison_preserves_cables_and_ignores_native_note_ids(self):
        second=copy.deepcopy(CANVAS);second['notes'][0]['id']='changed-native-id'
        self.assertEqual(presentation(CANVAS),presentation(second))
        second['devices'][0]['x']=11
        self.assertNotEqual(presentation(CANVAS),presentation(second))
        second=copy.deepcopy(CANVAS)
        second['links']=[{'dev_a':'synthetic','if_a':'Fa0','dev_b':'other','if_b':'Fa1'}]
        self.assertNotEqual(presentation(CANVAS),presentation(second))

    def test_default_mode_never_constructs_live_client(self):
        with patch('scripts.pt_integration.LiveBridge') as bridge,contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(main([]),0)
            bridge.assert_not_called()
            self.assertEqual(json.loads(output.getvalue())['live_verification'],'not_run')

    def test_live_mode_refuses_missing_confirmation_before_starting_java(self):
        with patch('scripts.pt_integration.LiveBridge') as bridge,contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):main(['--run-live'])
            bridge.assert_not_called()
