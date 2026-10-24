"""MCP contracts for offline planning/export and explicit build-copy presentation edits."""
import copy
import xml.etree.ElementTree as ET
import diagrams
import ptbuild
from ptread import parse


def schema(properties, required=()):
    return {'type':'object','properties':properties,'required':list(required),'additionalProperties':False}


SNAPSHOT = {'type':'object','description':'Canvas snapshot with devices/links/notes, or ptread topology.'}
PLAN = {'type':'object','description':'Plan from pt_layout_plan; partial plans are allowed.'}
TOOLS = [
    ('pt_layout_plan','Plan deterministic grouped/tiered positions and annotations. No mutations. Uses explicit snapshot or opened saved file.',
     schema({'snapshot':SNAPSHOT,'groups':{'type':'array','maxItems':50,'items':schema({
        'name':{'type':'string','minLength':1,'maxLength':256},
        'devices':{'type':'array','maxItems':500,'items':{'type':'string'}}},('name','devices'))}})),
    ('pt_export_svg','Export a portable SVG from a snapshot/opened saved file and optional plan. Does not apply the plan or save a project.',
     schema({'snapshot':SNAPSHOT,'plan':PLAN,'path':{'type':'string'},'title':{'type':'string','maxLength':256},
             'labels':{'type':'boolean','default':False},'overwrite':{'type':'boolean','default':False}},('path',))),
    ('pt_build_apply_layout','Apply plan positions to the offline working copy. Optional annotations create notes. Explicit save still required.',
     schema({'plan':PLAN,'add_annotations':{'type':'boolean','default':False}},('plan',))),
]


ANNOTATIONS = {'pt_layout_plan': {'readOnlyHint': True},
               'pt_export_svg': {'readOnlyHint': False},
               'pt_build_apply_layout': {'readOnlyHint': False}}

def handlers(require_read, require_build):
    def snapshot(args):
        if 'snapshot' in args: return args['snapshot']
        return require_read()['topo']

    def plan(args):
        return diagrams.plan_layout(snapshot(args),args.get('groups'))

    def export(args):
        return diagrams.export_svg(snapshot(args),args['path'],args.get('plan'),args.get('title','Network diagram'),
                                   args.get('labels',False),args.get('overwrite',False))

    def apply(args):
        build=require_build()
        topo=build['topo']
        plan=diagrams.validate_plan(args['plan'],parse(topo.root))
        add_notes=args.get('add_annotations',False)
        if not isinstance(add_notes,bool): raise ValueError('add_annotations must be boolean')
        # Preflight the complete set before touching the in-memory working copy.
        candidate=ptbuild.Topology(copy.deepcopy(topo.root))
        for move in plan['moves']:
            dev=candidate.device(move['name'])
            logical=dev.find('WORKSPACE/LOGICAL')
            if logical is None: raise ValueError('device lacks logical workspace: '+move['name'])
            for key in ('x','y'):
                el=logical.find(key.upper())
                if el is None: raise ValueError('device lacks position: '+move['name'])
                el.text=str(move[key])
        if add_notes:
            if candidate.root.find('PHYSICALWORKSPACE') is None:
                ET.SubElement(candidate.root,'PHYSICALWORKSPACE')
            for a in plan['annotations']: candidate.add_note(a['text'],a['x'],a['y'])
        readback=parse(candidate.root)
        by_name={d['name']:d for d in readback['by_ref'].values()}
        results=[{'name':m['name'],'x':int(by_name[m['name']]['x']),'y':int(by_name[m['name']]['y']),
                  'outcome':'success'} for m in plan['moves']]
        build['topo']=candidate
        build['log'].append({'op':'apply_layout','moves':len(results),
                             'annotations':len(plan['annotations']) if add_notes else 0})
        return {'outcome':'success','results':results,'saved':False,
                'annotations_added':len(plan['annotations']) if add_notes else 0}

    return {'pt_layout_plan':plan,'pt_export_svg':export,'pt_build_apply_layout':apply}
