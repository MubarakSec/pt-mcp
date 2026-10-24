import copy
import json
import pathlib
import tempfile
import unittest
import xml.etree.ElementTree as ET
import diagrams


def campus():
    devices=[{'name':'Core','type':'router'}]
    groups=[]
    links=[]
    for building,count in [('A',20),('B',20),('المبنى الثالث',10)]:
        switch='SW-'+building
        names=[switch]+[f'{building}-PC-{i:02}' for i in range(count)]
        groups.append({'name':building,'devices':names})
        devices += [{'name':n,'type':'switch' if n==switch else 'pc'} for n in names]
        links += [{'dev_a':'Core','dev_b':switch}]+[{'dev_a':switch,'dev_b':n} for n in names[1:]]
    return {'devices':devices,'links':links},groups


class DiagramTests(unittest.TestCase):
    def test_campus_repeatable_preserves_topology_and_bounds(self):
        snapshot,groups=campus(); original=copy.deepcopy(snapshot)
        plan=diagrams.plan_layout(snapshot,groups)
        self.assertEqual(plan,diagrams.plan_layout(snapshot,groups))
        self.assertEqual(snapshot,original)
        moves={m['name']:m for m in plan['moves']}
        self.assertEqual(set(moves),{d['name'] for d in snapshot['devices']})
        self.assertEqual(len(moves),len(plan['moves']))
        self.assertEqual(len({(m['x'],m['y']) for m in moves.values()}),len(moves))
        for group,region in zip(groups,plan['groups']):
            for name in group['devices']:
                m=moves[name]
                self.assertGreaterEqual(m['x'],region['x'])
                self.assertGreaterEqual(m['y'],region['y'])
                self.assertLess(m['x']+56,region['x']+region['width'])
                self.assertLess(m['y']+80,region['y']+region['height'])

    def test_empty_cycle_disconnected_and_xml(self):
        for snapshot in ({'devices':[],'links':[]}, {'devices':[{'name':'A'}, {'name':'B'}, {'name':'C'}],
                'links':[{'dev_a':'A','dev_b':'B'},{'dev_a':'B','dev_b':'A'}]}):
            plan=diagrams.plan_layout(snapshot)
            root=ET.fromstring(diagrams.render_svg(snapshot,plan))
            self.assertTrue(root.tag.endswith('svg'))
            self.assertEqual(len(plan['moves']),len(snapshot['devices']))
        name='العربية <&" '+ 'long'*50
        snapshot={'devices':[{'name':name,'x':-200,'y':0}], 'links':[{'dev_a':name,'dev_b':None}],
                  'notes':[{'text':'<script>alert(1)</script> العربية','x':0,'y':200}]}
        svg=diagrams.render_svg(snapshot)
        root=ET.fromstring(svg)
        self.assertNotIn('<script>',svg)
        self.assertIn('&lt;',svg)
        self.assertNotIn('http://', svg.replace('http://www.w3.org/2000/svg',''))
        self.assertIn('unknown',svg)
        self.assertTrue(any('العربية' in (e.text or '') for e in root.iter()))

    def test_invalid_inputs_preflight(self):
        snapshot,_=campus()
        invalid_groups=[ [{'name':'x','devices':['missing']}],
                         [{'name':'x','devices':['Core','Core']}],
                         [{'name':'x','devices':['Core']},{'name':'x','devices':[]}]]
        for groups in invalid_groups:
            with self.assertRaises(ValueError): diagrams.plan_layout(snapshot,groups)
        for value in (float('nan'),float('inf'),2**40):
            with self.assertRaises(ValueError): diagrams.render_svg({'devices':[{'name':'x','x':value,'y':0}]})
        with self.assertRaises(ValueError): diagrams.validate_plan({'moves':[{'name':'Core','x':1.5,'y':0}]},snapshot)
        with self.assertRaises(ValueError): diagrams.validate_plan({'moves':[{'name':'Core','x':1,'y':0}]*2},snapshot)
        with self.assertRaises(ValueError): diagrams.plan_layout({'devices':[{'name':'x'}]*501})

    def test_partial_plan_and_safe_export(self):
        snapshot={'devices':[{'name':'A','x':0,'y':0},{'name':'B','x':500,'y':600}],'links':[]}
        plan={'moves':[{'name':'A','x':100,'y':100}]}
        projected=diagrams.project(snapshot,plan)
        self.assertEqual(projected['devices'][1]['x'],500)
        with tempfile.TemporaryDirectory() as tmp:
            target=pathlib.Path(tmp)/'diagram.svg'
            result=diagrams.export_svg(snapshot,str(target),plan=plan)
            self.assertEqual(result['devices'],2)
            original=target.read_bytes()
            with self.assertRaises(FileExistsError): diagrams.export_svg(snapshot,str(target))
            self.assertEqual(original,target.read_bytes())
            diagrams.export_svg(snapshot,str(target),overwrite=True)
            with self.assertRaises(ValueError): diagrams.export_svg(snapshot,'relative.svg')
            other=pathlib.Path(tmp)/'other.svg';other.symlink_to(target)
            with self.assertRaises(ValueError): diagrams.export_svg(snapshot,str(other),overwrite=True)
