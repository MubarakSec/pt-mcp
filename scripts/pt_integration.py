#!/usr/bin/env python3
"""Opt-in disposable local Packet Tracer acceptance; defaults to a no-IPC plan."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import subprocess
import xml.etree.ElementTree as ET
import time
import uuid

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from live_bridge import LiveBridge,LiveBridgeError

MUTATIONS=frozenset({'pt_live_add_device','pt_live_rename_device','pt_live_move_device',
    'pt_live_add_note','pt_live_update_note','pt_live_delete_note','pt_live_connect_devices',
    'pt_live_run_cli_batch','pt_live_run_cli','pt_live_set_endpoint_dhcp',
    'pt_live_save_file','pt_live_open_file','pt_live_skip_boot'})


class IntegrationError(RuntimeError):
    def __init__(self,message,status='unknown'):
        super().__init__(message);self.status=status


def payload(result):
    if isinstance(result.get('structuredContent'),dict):return result['structuredContent']
    for content in result.get('content',[]):
        if content.get('type')=='text':
            try:
                value=json.loads(content['text'])
                if isinstance(value,dict):return value
            except (ValueError,KeyError):pass
    return {}


def presentation(snapshot):
    """Stable observable content, independent of native IDs and device-list order."""
    devices=sorted((d['name'],float(d['x']),float(d['y']),d.get('type'),d.get('model')) for d in snapshot['devices'])
    links=[]
    for link in snapshot['links']:
        ends=sorted(((link.get('dev_a') or '',link.get('if_a') or ''),(link.get('dev_b') or '',link.get('if_b') or '')))
        links.append((ends[0],ends[1],link.get('cable_type')))
    notes=sorted((n['text'],int(n['x']),int(n['y'])) for n in snapshot['notes'])
    return {'devices':devices,'links':sorted(links),'notes':notes}


class Harness:
    def __init__(self,client,directory,*,save_reopen=False,wait_seconds=90,skip_boot=False,exercise_terminal_timeout=False,exercise_failures=False):
        self.client=client;self.directory=Path(directory);self.allow_save=save_reopen
        self.wait_seconds=wait_seconds;self.skip_boot=skip_boot;self.exercise_terminal_timeout=exercise_terminal_timeout
        self.exercise_failures=exercise_failures
        self.prefix='PTMCP-'+uuid.uuid4().hex[:8]
        self.names={role:self.prefix+'-'+role for role in ('R1','SW1','SW2','PC1')}
        self.cleared_workspace=False
        self.report={'status':'unknown','live_verification':'pending','fixture_prefix':self.prefix,'steps':[],
                     'save_reopen_requested':save_reopen,'terminal_timeout_requested':exercise_terminal_timeout,
                     'negative_cases_requested':exercise_failures}

    def call(self,name,args=None,*,expected_error=False):
        if name in MUTATIONS and not self.cleared_workspace:
            raise IntegrationError('Refusing mutation before verifying an empty disposable workspace','fail')
        record={'tool':name,'arguments':args or {}}
        self.report['steps'].append(record)
        try:result=self.client.call_tool(name,args or {})
        except (LiveBridgeError,ValueError):
            record['status']='unknown';record['reason']='reply_lost_or_backend_unavailable'
            raise IntegrationError('Operation outcome unknown; inspect PT. No action was replayed.')
        observed=payload(result);record['observation']=observed
        record['tool_error']=bool(result.get('isError'))
        if result.get('isError') and not expected_error:
            outcome=observed.get('outcome')
            raise IntegrationError('Tool failed; partial changes may exist. Inspect PT before continuing.',
                                   'unknown' if outcome in ('unknown','partial') else 'fail')
        return observed

    def require(self,condition,message,status='fail'):
        if not condition:raise IntegrationError(message,status)

    def preflight(self):
        probe=self.call('pt_live_probe_connection',{'timeout_ms':10000})
        self.require(probe.get('status')=='pass','Authenticated IPC probe did not pass',
                     'fail' if probe.get('status')=='fail' else 'unknown')
        canvas=self.call('pt_live_get_canvas',{'include_empty_notes':True})
        self.require(all(isinstance(canvas.get(k),list) for k in ('devices','links','notes')),
                     'Canvas completeness is unknown','unknown')
        self.require(not canvas['devices'] and not canvas['links'] and not canvas['notes'],
                     'Active workspace is not empty; no mutations were sent')
        self.cleared_workspace=True

    def wait_boot(self):
        end=time.monotonic()+self.wait_seconds
        devices=[self.names[k] for k in ('R1','SW1','SW2')]
        if self.skip_boot:
            for name in devices:self.call('pt_live_skip_boot',{'name':name})
        while time.monotonic()<end:
            result=self.call('pt_live_validate_network',{'checks':[{'kind':'boot','device':n} for n in devices],
                                                       'timeout_ms':5000})
            if result.get('status')=='pass':return
            checks=result.get('checks',[])
            if any(c.get('status')=='unknown' for c in checks) or not checks:
                raise IntegrationError('Boot observation unavailable; inspect SDK evidence')
            time.sleep(0.5)
        raise IntegrationError('Devices did not finish booting within the harness deadline')

    def build(self):
        for role,kind,model,x,y in [('R1','router','2911',400,100),('SW1','switch','2960',250,250),
                                   ('SW2','switch','2960',600,250),('PC1','pc','PC-PT',600,450)]:
            created=self.call('pt_live_add_device',{'type':kind,'model':model,'x':x,'y':y,'name':self.names[role]})
            self.require(created.get('name')==self.names[role],'Named creation readback mismatch')
        self.wait_boot()
        for a,pa,b,pb in [('R1','GigabitEthernet0/0','SW1','FastEthernet0/1'),
                          ('SW1','GigabitEthernet0/1','SW2','GigabitEthernet0/1'),
                          ('SW2','FastEthernet0/1','PC1','FastEthernet0')]:
            linked=self.call('pt_live_connect_devices',{'device_a':self.names[a],'iface_a':pa,
                'device_b':self.names[b],'iface_b':pb,'cable_type':'auto'})
            self.require(linked.get('linked') is True,'Cable creation was not confirmed','unknown')
        commands=['interface GigabitEthernet0/0','ip address 192.0.2.1 255.255.255.0','no shutdown','exit',
                  'ip dhcp excluded-address 192.0.2.1 192.0.2.49','ip dhcp pool PTMCP-SCRATCH',
                  'network 192.0.2.0 255.255.255.0','default-router 192.0.2.1','exit']
        self.call('pt_live_run_cli_batch',{'device':self.names['R1'],'initial_mode':'global','commands':commands})
        for role in ('SW1','SW2'):
            commands=['vlan 10','name PTMCP-SCRATCH','exit','interface FastEthernet0/1',
                'switchport mode access','switchport access vlan 10','spanning-tree portfast','no shutdown','exit',
                'interface GigabitEthernet0/1','switchport mode trunk','switchport trunk allowed vlan 1,10','no shutdown','exit']
            self.call('pt_live_run_cli_batch',{'device':self.names[role],'initial_mode':'global','commands':commands})
        self.call('pt_live_set_endpoint_dhcp',{'device':self.names['PC1'],'iface':'FastEthernet0','enabled':True})

    def check_presentation(self):
        canvas=self.call('pt_live_get_canvas')
        self.require(len(canvas.get('links',[]))==3,'Scratch cable readback is incomplete','unknown')
        old=self.names['SW1'];new=old+'-Renamed'
        renamed=self.call('pt_live_rename_device',{'name':old,'new_name':new})
        self.require(renamed.get('name')==new,'Rename readback mismatch');self.names['SW1']=new
        moved=self.call('pt_live_move_device',{'name':new,'x':260,'y':270})
        self.require(moved.get('x')==260 and moved.get('y')==270,'Move readback mismatch')
        note=self.call('pt_live_add_note',{'text':'Readiness acceptance - scratch only','x':100,'y':30})
        self.require(bool(note.get('id')),'No native note identifier','unknown')
        updated=self.call('pt_live_update_note',{'id':note['id'],'text':'Readiness network 192.0.2.0/24'})
        self.require(updated.get('text')=='Readiness network 192.0.2.0/24','Note text readback mismatch')
        temporary=self.call('pt_live_add_note',{'text':'temporary acceptance note','x':10,'y':10})
        deleted=self.call('pt_live_delete_note',{'id':temporary['id']})
        self.require(deleted.get('removed') is True,'Note deletion was not confirmed')

    def checks(self):
        return [{'kind':'boot','device':self.names['R1']},
            {'kind':'dhcp_address','device':self.names['PC1'],'iface':'FastEthernet0'},
            *[{'kind':'trunk_vlan','device':self.names[s],'iface':'GigabitEthernet0/1','vlans':[10]} for s in ('SW1','SW2')]]

    def validate(self):
        passive=self.call('pt_live_validate_network',{'checks':self.checks()[1:]})
        self.require(all(c.get('reason')=='active_probe_required' for c in passive.get('checks',[]))
                     and len(passive.get('checks',[]))==3,'Default validation unexpectedly used active evidence')
        self.call('pt_live_get_readiness',{'devices':list(self.names.values()),'timeout_ms':5000})
        end=time.monotonic()+self.wait_seconds
        while time.monotonic()<end:
            result=self.call('pt_live_validate_network',{'checks':self.checks(),'allow_probes':True,'timeout_ms':10000})
            if result.get('status')=='pass':break
            checks=result.get('checks',[])
            self.require(bool(checks),'No network observations returned','unknown')
            # Only repeat fresh read probes after conclusive, completed observations.
            # Unknown output, timeouts or unresolved terminals never trigger another probe.
            if any(c.get('status')=='unknown' for c in checks):
                raise IntegrationError('Network evidence is unknown; inspect report, do not infer success')
            time.sleep(1)
        else:raise IntegrationError('DHCP/trunk forwarding did not pass within the harness deadline')
        address=result['checks'][1]['evidence'].get('observed_address','')
        self.require(address.startswith('192.0.2.'),'Observed address is outside the scratch DHCP subnet')
        negative=self.call('pt_live_validate_network',{'checks':[{'kind':'trunk_vlan','device':self.names['SW1'],
            'iface':'GigabitEthernet0/1','vlans':[3999]}],'allow_probes':True,'timeout_ms':5000})
        self.require(negative.get('status')=='fail','Negative VLAN assertion did not conclusively fail','unknown')
        idle=self.call('pt_live_validate_network',{'checks':[{'kind':'terminal_idle','device':self.names['PC1']}]})
        self.require(idle.get('status')=='pass','Completed ipconfig terminal did not become ready','unknown')

    def negative_cases(self):
        before=self.call('pt_live_get_canvas',{'include_empty_notes':True})
        collision=self.call('pt_live_add_device',{'type':'pc','model':'PC-PT','x':1,'y':1,'name':self.names['PC1']},expected_error=True)
        self.require(collision.get('outcome')=='validation_failure' and collision.get('changes_may_have_applied') is False,
                     'Creation collision was not rejected before mutation','unknown')
        collision=self.call('pt_live_rename_device',{'name':self.names['R1'],'new_name':self.names['SW1']},expected_error=True)
        self.require(collision.get('outcome')=='validation_failure' and collision.get('changes_may_have_applied') is False,
                     'Rename collision was not rejected before mutation','unknown')
        after=self.call('pt_live_get_canvas',{'include_empty_notes':True})
        self.require(presentation(before)==presentation(after),'Collision changed the observed canvas')
        baseline=self.call('pt_live_run_cli',{'device':self.names['SW1'],'mode':'enable','command':'show running-config'})
        # A 2960 normally has Fa0/1..24. If this selector is accepted, stop and leave
        # the disposable fixture for inspection; never guess a different failing range.
        marker='PTMCP-TAIL-MUST-NOT-RUN'
        failure=self.call('pt_live_run_cli_batch',{'device':self.names['SW1'],'initial_mode':'global',
            'commands':['interface range FastEthernet0/1-25','description '+marker]},expected_error=True)
        self.require(failure.get('failed')==[0] and failure.get('unattempted')==[1] and failure.get('unknown')==[],
                     'Interface-range failure did not produce a conclusive stop; inspect state before continuing','unknown')
        readback=self.call('pt_live_run_cli',{'device':self.names['SW1'],'mode':'enable','command':'show running-config'})
        self.require(bool(baseline.get('output')) and baseline.get('output')==readback.get('output') and marker not in readback.get('output',''),
                     'Configuration changed or range-failure readback is incomplete','unknown')
        self.report['negative_cases']='pass'

    def verify_saved_xml(self,path):
        decoded=self.directory/'scratch-decoded.xml'
        try:
            result=subprocess.run([sys.executable,str(ROOT/'unpacket.py'),str(path),'-o',str(decoded)],
                                  capture_output=True,text=True,timeout=60)
        except (OSError,subprocess.TimeoutExpired):
            raise IntegrationError('Saved project decoding did not complete; XML validity is unknown')
        self.require(result.returncode==0 and decoded.is_file(),'Saved project could not be decoded; XML validity is unknown','unknown')
        try:ET.parse(decoded)
        except ET.ParseError:raise IntegrationError('Saved XML is invalid; refusing to reopen the project','fail')
        self.report['saved_xml']='well_formed'

    def save_reopen(self):
        if not self.allow_save:raise IntegrationError('Save/reopen requires explicit --save-reopen','fail')
        path=self.directory/'scratch.pkt'
        self.require(not path.exists(),'Refusing to overwrite an existing project')
        before=self.call('pt_live_get_canvas')
        # --save-reopen explicitly authorizes startup-config persistence as well as .pkt save.
        for role in ('R1','SW1','SW2'):
            self.call('pt_live_run_cli',{'device':self.names[role],'command':'write memory','mode':'enable'})
        saved=self.call('pt_live_save_file',{'path':str(path)})
        self.require(saved.get('saved') is True,'PT did not confirm project save','unknown')
        self.require(path.is_file(),'Saved path is not visible locally; run harness on the PT host','unknown')
        self.verify_saved_xml(path)
        self.call('pt_live_open_file',{'path':str(path)})
        after=self.call('pt_live_get_canvas')
        self.require(presentation(before)==presentation(after),'Canvas devices/positions/notes/links changed after reopening')
        self.wait_boot();self.validate()
        self.report['save_reopen']='pass'

    def terminal_timeout(self):
        result=self.call('pt_live_run_terminal',{'device':self.names['PC1'],'command':'ping 203.0.113.254','timeout_ms':1})
        self.require(result.get('timedOut') is True,'Native command finished too quickly to exercise timeout','unknown')
        activity=result.get('terminal_activity',{}).get('evidence',{})
        token=activity.get('operation_id')
        self.require(isinstance(token,int),'No tracked operation ID was returned','unknown')
        end=time.monotonic()+self.wait_seconds
        while time.monotonic()<end:
            report=self.call('pt_live_get_terminal_result',{'device':self.names['PC1'],'operation_id':token,'timeout_ms':3000})
            if report.get('completed') is True:
                self.require(bool(report.get('output')),'Late terminal completion has no captured output','unknown')
                self.report['terminal_late_completion']='pass';return
            self.require(report.get('reason')=='terminal_result_pending','Terminal result is no longer observable','unknown')
            time.sleep(0.5)
        raise IntegrationError('No late terminal completion observed; inspect PT before any further command')

    def run(self):
        self.preflight();self.build();self.check_presentation();self.validate()
        if self.exercise_failures:self.negative_cases()
        if self.allow_save:self.save_reopen()
        if self.exercise_terminal_timeout:self.terminal_timeout()
        self.report['status']='pass';self.report['live_verification']='requested_checks_completed'
        return self.report


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-live',action='store_true')
    parser.add_argument('--confirm-empty-workspace',action='store_true')
    parser.add_argument('--scratch-dir',type=Path)
    parser.add_argument('--save-reopen',action='store_true')
    parser.add_argument('--skip-boot',action='store_true',help='Explicitly skip boot on scratch Cisco devices')
    parser.add_argument('--exercise-failures',action='store_true',help='Explicitly test naming collisions and a rejected interface-range with a guarded tail command')
    parser.add_argument('--exercise-terminal-timeout',action='store_true',help='Explicitly send one short-timeout ping and watch its late completion')
    parser.add_argument('--wait-seconds',type=int,default=90)
    args=parser.parse_args(argv)
    if not args.run_live:
        print(json.dumps({'mode':'plan_only','live_verification':'not_run',
            'requirements':['Local PT with registered IPC and legitimate SDK build','Empty disposable active PT workspace',
                            '--run-live --confirm-empty-workspace --scratch-dir /absolute/new-directory'],
            'fixture':'one router, two switches, one DHCP PC; VLAN 10 and a trunk',
            'saves':'only with --save-reopen; startup configs and a new scratch.pkt'},indent=2))
        return 0
    if not args.confirm_empty_workspace or args.scratch_dir is None or not args.scratch_dir.is_absolute():
        parser.error('live execution requires --confirm-empty-workspace and an absolute --scratch-dir')
    if not 1<=args.wait_seconds<=300:parser.error('--wait-seconds must be 1..300')
    if args.scratch_dir.exists() or args.scratch_dir.is_symlink():parser.error('--scratch-dir must be a new path')
    args.scratch_dir.mkdir(mode=0o700)
    client=None
    harness=Harness(client,args.scratch_dir,save_reopen=args.save_reopen,wait_seconds=args.wait_seconds,
                    skip_boot=args.skip_boot,exercise_terminal_timeout=args.exercise_terminal_timeout,exercise_failures=args.exercise_failures)
    try:
        client=LiveBridge();harness.client=client
        harness.run()
    except IntegrationError as error:
        harness.report.update(status=error.status,reason=str(error),live_verification='incomplete')
    except Exception:
        harness.report.update(status='unknown',reason='Harness stopped unexpectedly; inspect scratch project and report',live_verification='incomplete')
    finally:
        if client is not None:client.close()
        with (args.scratch_dir/'report.json').open('x',encoding='utf-8') as out:
            json.dump(harness.report,out,ensure_ascii=False,indent=2)
        print(json.dumps({'status':harness.report['status'],'report':str(args.scratch_dir/'report.json')}))
    return 0 if harness.report['status']=='pass' else 1


if __name__=='__main__':raise SystemExit(main())
