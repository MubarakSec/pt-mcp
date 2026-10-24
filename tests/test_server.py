import json
import os
import pathlib
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET

ROOT=pathlib.Path(__file__).resolve().parents[1]
FIXTURE='''<PACKETTRACER5><NETWORK><DEVICES>
<DEVICE><ENGINE><SAVE_REF_ID>1</SAVE_REF_ID><NAME>R1</NAME><TYPE>router</TYPE><RUNNINGCONFIG><LINE>hostname original</LINE></RUNNINGCONFIG></ENGINE><WORKSPACE><LOGICAL><X>5</X><Y>6</Y></LOGICAL></WORKSPACE></DEVICE>
<DEVICE><ENGINE><SAVE_REF_ID>2</SAVE_REF_ID><NAME>PC1</NAME><TYPE>pc</TYPE></ENGINE><WORKSPACE><LOGICAL><X>15</X><Y>16</Y></LOGICAL></WORKSPACE></DEVICE>
</DEVICES><LINKS><LINK><CABLE><FROM>1</FROM><TO>2</TO><PORT>g0/0</PORT><PORT>fa0</PORT></CABLE></LINK></LINKS></NETWORK><PHYSICALWORKSPACE><NOTES/></PHYSICALWORKSPACE></PACKETTRACER5>'''


class ServerTests(unittest.TestCase):
    def test_real_stdio_offline_workflows_and_live_failure_isolation(self):
        with tempfile.TemporaryDirectory() as tmp:
            source=pathlib.Path(tmp)/'synthetic.xml';source.write_text(FIXTURE)
            svg=pathlib.Path(tmp)/'campus.svg'
            env=dict(os.environ,PT_MCP_LIVE_COMMAND=json.dumps(['/no/pt-mcp-backend']))
            requests=[('initialize',{}),('tools/list',{})]
            def call(name,args): requests.append(('tools/call',{'name':name,'arguments':args}))
            call('pt_open',{'path':str(source)})
            call('pt_layout_plan',{})
            call('pt_export_svg',{'path':str(svg),'title':'العربية & <campus>'})
            call('pt_live_get_canvas',{})
            call('pt_devices',{})
            call('pt_build_open',{'path':str(source)})
            call('pt_build_apply_layout',{'plan':{'moves':[{'name':'R1','x':100,'y':200}]}})
            call('pt_build_apply_layout',{'plan':{'moves':[{'name':'R1','x':9,'y':9},{'name':'missing','x':0,'y':0}]}})
            call('pt_build_status',{})
            wire=''.join(json.dumps({'jsonrpc':'2.0','id':i,'method':m,'params':p})+'\n' for i,(m,p) in enumerate(requests))
            process=subprocess.run([sys.executable,str(ROOT/'server.py')],input=wire,text=True,capture_output=True,env=env,timeout=15)
            self.assertEqual(process.returncode,0,process.stderr)
            replies=[json.loads(line) for line in process.stdout.splitlines()]
            self.assertEqual(len(replies),len(requests))
            self.assertEqual([r['id'] for r in replies],list(range(len(requests))))
            tools=replies[1]['result']['tools'];names=[t['name'] for t in tools]
            self.assertEqual(len(names),len(set(names)))
            self.assertIn('pt_live_apply_layout',names)
            self.assertIn('pt_layout_plan',names)
            self.assertEqual(len(names),63)
            self.assertTrue(next(t for t in tools if t['name']=='pt_layout_plan')['annotations']['readOnlyHint'])
            for i in (2,3,4,6,7,8,10): self.assertFalse(replies[i]['result'].get('isError'),replies[i])
            self.assertTrue(replies[5]['result']['isError'])
            self.assertTrue(replies[9]['result']['isError'])
            plan=json.loads(replies[3]['result']['content'][0]['text'])
            self.assertEqual(len(plan['moves']),2)
            ET.parse(svg)
            self.assertEqual(source.read_text(),FIXTURE)

    def test_offline_apply_preserves_links_configs_and_preflight(self):
        import diagram_tools,ptbuild
        topo=ptbuild.Topology(ET.fromstring(FIXTURE))
        state={'topo':topo,'log':[]}
        handlers=diagram_tools.handlers(lambda:None,lambda:state)
        before_links=ET.tostring(topo.links)
        before_config=ET.tostring(topo.device('R1').find('ENGINE/RUNNINGCONFIG'))
        result=handlers['pt_build_apply_layout']({'plan':{'moves':[{'name':'R1','x':100,'y':200}],
            'annotations':[{'text':'المبنى الأول','x':0,'y':0}]},'add_annotations':True})
        self.assertFalse(result['saved'])
        self.assertEqual(ET.tostring(state['topo'].links),before_links)
        self.assertEqual(ET.tostring(state['topo'].device('R1').find('ENGINE/RUNNINGCONFIG')),before_config)
        self.assertEqual(state['topo'].device('PC1').findtext('WORKSPACE/LOGICAL/X'),'15')
        before=ET.tostring(state['topo'].root)
        with self.assertRaises(ValueError):
            handlers['pt_build_apply_layout']({'plan':{'moves':[{'name':'R1','x':4,'y':4},{'name':'missing','x':0,'y':0}]}})
        self.assertEqual(before,ET.tostring(state['topo'].root))
