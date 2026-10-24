"""Deterministic presentation planning and self-contained SVGs. No simulator access."""
from __future__ import annotations

import copy
import math
import os
from pathlib import Path
import textwrap
import unicodedata
import xml.etree.ElementTree as ET

MAX_DEVICES = 500
MAX_LINKS = 2000
MAX_NOTES = 500
MAX_GROUPS = 50
NS = 'http://www.w3.org/2000/svg'
ET.register_namespace('', NS)


def label(value, limit=256):
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise ValueError(f'text must contain 1..{limit} characters')
    if any((ord(c) < 32 and c not in '\n\t') or 0xD800 <= ord(c) <= 0xDFFF
           or ord(c) in (0xFFFE, 0xFFFF) for c in value):
        raise ValueError('text contains invalid XML characters')
    return value


def valid_name(value):
    value = label(value)
    if any(unicodedata.category(c) == 'Cc' for c in value):
        raise ValueError('names must not contain control characters')
    return value


def coordinate(value, integer=False):
    if isinstance(value, bool):
        raise ValueError('coordinates must be numeric')
    try:
        number = float(value)
    except (ValueError, TypeError, OverflowError) as exc:
        raise ValueError('coordinates must be numeric') from exc
    if not math.isfinite(number) or not -(2**31) <= number <= 2**31-1:
        raise ValueError('coordinates must be finite and within signed 32-bit range')
    if integer and (not isinstance(value, (int, float)) or number != int(number)):
        raise ValueError('move coordinates must be signed 32-bit integers')
    return int(number) if integer else number


def _bounded_list(value, maximum, kind):
    if not isinstance(value, list) or len(value) > maximum or any(not isinstance(v, dict) for v in value):
        raise ValueError(f'{kind} must be a list of at most {maximum} objects')
    return value


def snapshot_data(snapshot):
    if not isinstance(snapshot, dict):
        raise ValueError('snapshot must be an object')
    devices = snapshot.get('devices', [])
    if 'by_ref' in snapshot:  # ptread's ordered reference list
        devices = list(snapshot['by_ref'].values())
    if isinstance(devices, dict):  # explicit SAVE_REF_ID map
        devices = list(devices.values())
    devices = _bounded_list(devices, MAX_DEVICES, 'devices')
    result = {'devices': [], 'links': [], 'notes': []}
    names = set()
    for d in devices:
        device_name = valid_name(d.get('name'))
        if device_name in names:
            raise ValueError('duplicate device name: ' + device_name)
        names.add(device_name)
        device = copy.deepcopy(d)
        device.update(name=device_name, x=coordinate(d.get('x') if d.get('x') not in (None, '') else 0),
                      y=coordinate(d.get('y') if d.get('y') not in (None, '') else 0))
        for key in ('type', 'model'):
            value = device.get(key)
            if value is None: value = ''
            if not isinstance(value, str): raise ValueError(key+' must be a string')
            if value: label(value)
            device[key] = value
        result['devices'].append(device)
    for link in _bounded_list(snapshot.get('links', []), MAX_LINKS, 'links'):
        item = copy.deepcopy(link)
        item['dev_a'] = link.get('dev_a', link.get('from'))
        item['dev_b'] = link.get('dev_b', link.get('to'))
        item['if_a'] = link.get('if_a', link.get('from_port', ''))
        item['if_b'] = link.get('if_b', link.get('to_port', ''))
        item['cable_type'] = link.get('cable_type', link.get('type', ''))
        # Saved FUNCTIONAL does not establish current link health.
        item['state'] = link.get('state') if link.get('state') in ('up', 'down') else 'unknown'
        for key in ('dev_a','dev_b','if_a','if_b','cable_type'):
            if item[key] is not None and item[key] != '': label(item[key])
        result['links'].append(item)
    for note in _bounded_list(snapshot.get('notes', []), MAX_NOTES, 'notes'):
        item = copy.deepcopy(note)
        value = note.get('text', '')
        if not isinstance(value, str) or len(value) > 16384: raise ValueError('invalid note text')
        item['text'] = label(value, 16384) if value.strip() else ''
        item['x'] = coordinate(note.get('x') or 0)
        item['y'] = coordinate(note.get('y') or 0)
        result['notes'].append(item)
    return result


def tier(device):
    kind = (device.get('type', '') + ' ' + device.get('model', '')).lower()
    if any(x in kind for x in ('router', 'asa', 'firewall')): return 0
    if any(x in kind for x in ('multi_layer', 'multilayer', 'core')): return 1
    if any(x in kind for x in ('switch', 'hub', 'access_point')): return 2
    return 3


def _lines(value, width=26):
    return [line for part in value.splitlines() for line in (textwrap.wrap(part, width=width) or [''])] or ['']


def plan_layout(snapshot, groups=None):
    data = snapshot_data(snapshot)
    groups = _bounded_list([] if groups is None else groups, MAX_GROUPS, 'groups')
    by_name = {d['name']: d for d in data['devices']}
    used, group_names, regions = set(), set(), []
    for group in groups:
        name = valid_name(group.get('name'))
        members = group.get('devices')
        if name in group_names or not isinstance(members, list) or len(members) > MAX_DEVICES:
            raise ValueError('duplicate group name or invalid membership')
        group_names.add(name)
        for member in members:
            valid_name(member)
            if member not in by_name or member in used:
                raise ValueError('unknown device or duplicate membership: ' + member)
            used.add(member)
        regions.append((name, sorted(members)))
    remaining = sorted(set(by_name)-used)
    shared_name = None
    if remaining or not regions:
        fallback = 'Ungrouped'
        while fallback in group_names: fallback += ' '
        regions.append((fallback, remaining))
        if groups and remaining: shared_name = fallback
    moves, bounds, annotations = [], [], []
    region_x = 40
    group_top = 40
    if shared_name:
        columns = min(5, max(1, math.ceil(math.sqrt(len(remaining)))))
        cell_h = max([140]+[80+18*len(_lines(n)) for n in remaining])
        rows = sum(math.ceil(sum(tier(by_name[n]) == level for n in remaining)/columns) for level in range(4))
        group_top = 40 + max(180, 100+20*len(_lines(shared_name))+rows*cell_h) + 60
    for name, members in regions:
        columns = min(5, max(1, math.ceil(math.sqrt(len(members)))))
        cell_w = 230
        cell_h = max([140]+[80+18*len(_lines(n)) for n in members])
        heading_h = 40 + 20*len(_lines(name))
        width = max(300, columns*cell_w+80)
        base_y = group_top if shared_name and name != shared_name else 40
        if name == shared_name: region_x = max(40, int((region_x-60-width)/2))
        y = base_y+20+heading_h
        for level in range(4):
            row = sorted((n for n in members if tier(by_name[n]) == level))
            for i, n in enumerate(row):
                moves.append({'name': n, 'x': region_x+70+(i % columns)*cell_w,
                              'y': y+(i // columns)*cell_h})
            if row: y += math.ceil(len(row)/columns)*cell_h
        height = max(180, y+40-base_y)
        bounds.append({'name': name, 'x': region_x, 'y': base_y, 'width': width, 'height': height})
        annotations.append({'text': name, 'x': region_x+24, 'y': base_y+20})
        region_x += width+60
    return {'version': 1, 'layout': 'grouped' if groups else 'tiered',
            'coordinate_contract': 'icon origin; signed 32-bit integers',
            'moves': moves, 'groups': bounds, 'annotations': annotations}


def validate_plan(plan, snapshot):
    if not isinstance(plan, dict): raise ValueError('plan must be an object')
    data = snapshot_data(snapshot)
    known = {d['name'] for d in data['devices']}
    moves = _bounded_list(plan.get('moves', []), MAX_DEVICES, 'moves')
    seen = set()
    normalized = copy.deepcopy(plan)
    normalized['moves'] = []
    for m in moves:
        n = valid_name(m.get('name'))
        if n not in known or n in seen: raise ValueError('unknown/duplicate move: ' + n)
        seen.add(n)
        normalized['moves'].append({'name': n, 'x': coordinate(m.get('x'), True), 'y': coordinate(m.get('y'), True)})
    normalized['groups'] = []
    group_names = set()
    for g in _bounded_list(plan.get('groups', []), MAX_GROUPS+1, 'groups'):
        n = valid_name(g.get('name'))
        if n in group_names: raise ValueError('duplicate group name')
        group_names.add(n)
        region = {'name': n, **{k: coordinate(g.get(k)) for k in ('x','y','width','height')}}
        if region['width'] <= 0 or region['height'] <= 0: raise ValueError('group bounds must be positive')
        normalized['groups'].append(region)
    normalized['annotations'] = []
    for a in _bounded_list(plan.get('annotations', []), MAX_NOTES, 'annotations'):
        normalized['annotations'].append({'text': label(a.get('text'), 16384),
            'x': coordinate(a.get('x'), True), 'y': coordinate(a.get('y'), True)})
    return normalized


def project(snapshot, plan=None):
    data = snapshot_data(snapshot)
    if plan is not None:
        plan = validate_plan(plan, data)
        positions = {m['name']: m for m in plan['moves']}
        for d in data['devices']:
            if d['name'] in positions: d.update(positions[d['name']])
    return data


def render_svg(snapshot, plan=None, title='Network diagram', labels=False):
    label(title)
    if not isinstance(labels, bool): raise ValueError('labels must be boolean')
    data = project(snapshot, plan)
    groups = validate_plan(plan, data)['groups'] if plan is not None else []
    notes = list(data['notes'])
    if plan is not None:
        # Group annotations already appear as region headings. Render any other explicit annotations.
        for a in validate_plan(plan, data)['annotations']:
            if a['text'] not in {g['name'] for g in groups}: notes.append(a)
    extents = [(0,0,max(760,min(60,len(title))*14),100)]
    for d in data['devices']: extents.append((d['x']-100,d['y']-10,260,80+18*len(_lines(d['name']))))
    for n in notes: extents.append((n['x'],n['y'],300,30+18*len(_lines(n['text'],36))))
    extents += [(g['x'],g['y'],g['width'],g['height']) for g in groups]
    left=min(x for x,y,w,h in extents)-40; top=min(y for x,y,w,h in extents)-(60+18*len(_lines(title,60)))
    right=max(x+w for x,y,w,h in extents)+40; bottom=max(y+h for x,y,w,h in extents)+70
    def node(tag, attrs=None, parent=None, text=None):
        result=ET.SubElement(parent if parent is not None else root, '{'+NS+'}'+tag, {k:str(v) for k,v in (attrs or {}).items()})
        result.text=text; return result
    root=ET.Element('{'+NS+'}svg', {'viewBox':f'{left} {top} {right-left} {bottom-top}', 'role':'img'})
    node('title',text=title)
    node('rect',{'x':left,'y':top,'width':right-left,'height':bottom-top,'fill':'#f8fafc'})
    def text_at(value,x,y,width=26,size=14,anchor='middle',fill='#172033'):
        rtl=next((unicodedata.bidirectional(c) for c in value if unicodedata.bidirectional(c) in ('L','R','AL')),'L') in ('R','AL')
        t=node('text',{'x':x,'y':y,'font-family':'sans-serif','font-size':size,'fill':fill,
                       'text-anchor':anchor,'stroke':'#f8fafc','stroke-width':3,'paint-order':'stroke fill','stroke-linejoin':'round','direction':'rtl' if rtl else 'ltr','unicode-bidi':'plaintext'})
        for i,line in enumerate(_lines(value,width)):
            node('tspan',{'x':x,'dy':0 if i==0 else 18},parent=t,text=line)
    text_at(title,left+30,top+34,60,22,'start')
    for g in groups:
        node('rect',{'x':g['x'],'y':g['y'],'width':g['width'],'height':g['height'],'rx':14,'fill':'#edf2f7','stroke':'#a8b5c6'})
        text_at(g['name'],g['x']+g['width']/2,g['y']+28,26,17)
    by_name={d['name']:d for d in data['devices']}
    omitted=0
    for link in data['links']:
        a=by_name.get(link['dev_a']); b=by_name.get(link['dev_b'])
        if a is None or b is None: omitted+=1; continue
        state=link['state']
        color={'up':'#168064','down':'#bc3b3b','unknown':'#8793a5'}[state]
        line=node('line',{'x1':a['x']+28,'y1':a['y']+20,'x2':b['x']+28,'y2':b['y']+20,
                          'stroke':color,'stroke-width':2,'stroke-dasharray':'6 4' if state=='unknown' else 'none'})
        node('title',parent=line,text=f"{link['dev_a']} ↔ {link['dev_b']}: {state}")
        if labels:
            text_at(f"{link['if_a']} — {link['if_b']} ({link['cable_type']})",(a['x']+b['x'])/2+28,(a['y']+b['y'])/2,30,11)
    for d in data['devices']:
        x,y=d['x'],d['y']; level=tier(d)
        kind=(d.get('type','')+' '+d.get('model','')).lower()
        node('rect',{'x':x,'y':y,'width':56,'height':40,'rx':20 if level==0 else 5,'fill':'#fff','stroke':'#254863','stroke-width':2})
        if level==0:
            text_at('↔',x+28,y+27,26,24)
        elif level in (1,2):
            for i in range(4): node('rect',{'x':x+8+i*11,'y':y+17,'width':7,'height':7,'fill':'#254863'})
        elif any(k in kind for k in ('pc','host','server','laptop')):
            node('rect',{'x':x+10,'y':y+7,'width':36,'height':22,'fill':'#e1edf6','stroke':'#254863'})
            node('path',{'d':f'M {x+20} {y+35} h 16','stroke':'#254863','stroke-width':2})
        else: text_at('?',x+28,y+27,26,22)
        text_at(d['name'],x+28,y+62)
    for n in notes:
        if n['text']: text_at(n['text'],n['x'],n['y']+18,36,13,'start','#536177')
    text_at(f"Observed links only · dashed gray = unknown · {omitted} links omitted (unresolved endpoints)",left+30,bottom-24,110,12,'start','#536177')
    return ET.tostring(root,encoding='unicode',xml_declaration=True)


def export_svg(snapshot, path, plan=None, title='Network diagram', labels=False, overwrite=False):
    if not isinstance(path,str) or not Path(path).is_absolute(): raise ValueError('SVG path must be absolute')
    if not isinstance(overwrite,bool): raise ValueError('overwrite must be boolean')
    target=Path(path)
    if target.is_symlink(): raise ValueError('refusing a symbolic-link output')
    svg=render_svg(snapshot,plan,title,labels)
    # O_EXCL prevents accidental overwrites, O_NOFOLLOW also closes the final symlink race.
    flags=os.O_WRONLY|os.O_CREAT|(os.O_TRUNC if overwrite else os.O_EXCL)|getattr(os,'O_NOFOLLOW',0)
    fd=os.open(target,flags,0o644)
    with os.fdopen(fd,'w',encoding='utf-8') as stream: stream.write(svg+'\n')
    data=snapshot_data(snapshot);known={d['name'] for d in data['devices']}
    omitted=sum(l['dev_a'] not in known or l['dev_b'] not in known for l in data['links'])
    return {'path':str(target),'devices':len(data['devices']),'links':len(data['links'])-omitted,
            'notes':len(data['notes']),'omitted_links':omitted,'unsupported_elements':(['saved canvas graphics/labels'] if snapshot.get('labels') else [])}
