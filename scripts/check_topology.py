#!/usr/bin/env python3
"""Check standalone SVG structure, links, interface text and naming groups."""
import argparse
import json
import math
from pathlib import Path
import re
import sys
import xml.etree.ElementTree as ET

from layout_engine import line_hits_box, overlaps, text_box


class Report:
    def __init__(self):self.errors=[];self.warnings=[]
    def error(self,value):self.errors.append(value)
    def warn(self,value):self.warnings.append(value)


def tag(e):return e.tag.rsplit('}',1)[-1]


def validate_svg(data,require_viewbox=True):
    if b'<!DOCTYPE' in data.upper() or b'<!ENTITY' in data.upper():raise ValueError('不允许实体或外部 DTD')
    root=ET.fromstring(data)
    if tag(root)!='svg' or (require_viewbox and not root.get('viewBox')):raise ValueError('需要带 viewBox 的 SVG')
    elements=list(root.iter());ids=[e.get('id') for e in elements if e.get('id')]
    if len(ids)!=len(set(ids)):raise ValueError('存在重复的 SVG id')
    ids=set(ids)
    for e in elements:
        if tag(e) in {'script','image','foreignObject','iframe'}:raise ValueError('SVG 必须由内联矢量和文字组成')
        for k,v in e.attrib.items():
            key=k.rsplit('}',1)[-1].lower()
            if key.startswith('on'):raise ValueError('不允许 SVG 事件处理器')
            if key in {'href','src'} and (not v.startswith('#') or v[1:] not in ids):raise ValueError('引用资源未内联')
            for url in re.findall(r'url\s*\(\s*[\x22\x27]?([^\x22\x27)\s]+)',v,re.I):
                if not url.startswith('#') or url[1:] not in ids:raise ValueError('不允许外部资源')
        if tag(e)=='style' and re.search(r'@import|https?:|data:',e.text or '',re.I):raise ValueError('不允许外部样式')
    return root


def _collinear_overlap(a,b,c,d):
    dx,dy=b[0]-a[0],b[1]-a[1];length=math.hypot(dx,dy)
    if length<1e-6:return False
    if any(abs(dx*(p[1]-a[1])-dy*(p[0]-a[0]))/length>.1 for p in (c,d)):return False
    project=lambda p:((p[0]-a[0])*dx+(p[1]-a[1])*dy)/length
    start,end=sorted((project(c),project(d)))
    return min(length,end)-max(0,start)>1


def validate(data,icon=False):
    r=Report()
    try:root=validate_svg(data,not icon)
    except (ValueError,ET.ParseError) as exc:r.error(str(exc));return r
    if icon:
        if root.get('viewBox') not in (None,'0 0 64 64'):r.error('图标 viewBox 应为 0 0 64 64')
        if root.get('viewBox') is None and not any(tag(e)=='symbol' for e in root):r.error('图标集合缺少 symbol')
        return r
    try:
        vx,vy,w,h=map(float,root.get('viewBox','').replace(',',' ').split())
        if not all(math.isfinite(n) for n in (vx,vy,w,h)) or w<=0 or h<=0:raise ValueError()
    except ValueError:r.error('viewBox 应为四个有限数字，宽高为正');return r
    if not any(tag(e)=='rect' and e.get('fill','').lower() in {'#fff','#ffffff','white'} and e.get('width') in {'100%',str(int(w)),str(w)} for e in root):r.error('缺少完整白色背景')
    elements=list(root.iter())
    devices=[e for e in elements if e.get('data-role')=='device']
    centers={e.get('data-device'):tuple(map(float,e.get('data-center').split())) for e in devices if e.get('data-center')}
    names=[e for e in elements if e.get('data-role')=='device-name']
    dots=[(float(e.get('cx')),float(e.get('cy'))) for e in elements if e.get('data-role')=='port']
    wires=[];wireless=[]
    for e in elements:
        role=e.get('data-role')
        if role not in {'link','wireless-link'}:continue
        values=[float(v) for v in re.findall(r'-?\d+(?:\.\d+)?',e.get('points',e.get('d','')))]
        if len(values)<4 or len(values)%2:r.error('链路坐标无效');continue
        points=list(zip(values[::2],values[1::2]))
        if e.get('data-routing')=='radial' and len(points)==2:
            a,b=points;length=math.dist(a,b)
            for owner in (e.get('data-from'),e.get('data-to')):
                if owner in centers and length>0:
                    cx,cy=centers[owner]
                    if abs((b[0]-a[0])*(cy-a[1])-(b[1]-a[1])*(cx-a[0]))/length>1:r.error('直连接点未沿设备方向对齐：'+owner)
        if any(not (vx<=x<=vx+w and vy<=y<=vy+h) for x,y in points):r.error('链路越界')
        (wires if role=='link' else wireless).append(points)
        if role=='link':
            for point in (points[0],points[-1]):
                if not any(math.dist(point,d)<.15 for d in dots):r.error('物理链路端点缺少绿色接口点')
        owners={e.get('data-from'),e.get('data-to')}
        for device in devices:
            if device.get('data-device') in owners or not device.get('data-bounds'):continue
            box=tuple(map(float,device.get('data-bounds').split()))
            if any(line_hits_box(a,b,box,pad=0) for a,b in zip(points,points[1:])):r.error('连线经过其他设备：'+device.get('data-device',''))
    for i,line in enumerate(wires):
        for other in wires[i+1:]:
            if any(_collinear_overlap(a,b,c,d) for a,b in zip(line,line[1:]) for c,d in zip(other,other[1:])):r.error('不同物理链路共用一段线')
    texts=[]
    def walk(e,inside=False):
        if tag(e) in {'metadata','defs','symbol','title','desc'}:return
        if e.get('data-role')=='device':return
        if tag(e)=='text':
            value=''.join(e.itertext());x=float(e.get('x','0'));y=float(e.get('y','0'));size=float(e.get('font-size','16'))
            box=text_box(value,x,y,size,e.get('text-anchor','start'))
            texts.append((box,value))
            if box[0]<vx or box[1]<vy or box[2]>vx+w or box[3]>vy+h:r.error('文字越界：'+value)
            if e.get('data-role')=='title' or re.match(r'^B\d{3}\s+\S',value):r.error('图内不应出现实验标题')
        for child in e:walk(child,inside)
    try:walk(root)
    except ValueError:r.error('文字坐标无效')
    for i,(box,value) in enumerate(texts):
        for other,label in texts[i+1:]:
            if overlaps(box,other,pad=-2):r.warn('文字可能相交：'+value+' / '+label)
        if any(line_hits_box(a,b,box,pad=0) for line in wires+wireless for a,b in zip(line,line[1:])):r.warn('连线可能经过文字：'+value)
    for name in names:
        if name.get('data-placement') not in {'S','N','E','W','SE','SW','NE','NW'}:r.error('设备名未使用八个标准方位')
    if root.get('data-fit')=='content' and root.get('data-content-bounds'):
        try:
            x1,y1,x2,y2=map(float,root.get('data-content-bounds').split())
            if abs((x1-vx)-(vx+w-x2))>1 or abs((y1-vy)-(vy+h-y2))>1:r.error('内容未居中，留白不对称')
        except ValueError:r.error('内容范围元数据无效')
    for group in elements:
        if group.get('data-role')=='port-label' and sum(tag(e)=='text' for e in group)>1:r.error('接口编号组不能混入 IP、VLAN 等补充信息')
        if group.get('data-role')=='port-label' and group.get('data-endpoint'):
            px,py=map(float,group.get('data-endpoint').split())
            child=next((e for e in group if tag(e)=='text'),None)
            if child is not None:
                box=text_box(''.join(child.itertext()),float(child.get('x')),float(child.get('y')),float(child.get('font-size',15)),child.get('text-anchor','start'))
                distance=math.hypot(max(box[0]-px,0,px-box[2]),max(box[1]-py,0,py-box[3]))
                if distance>64:r.warn('接口编号距离绿点过远：'+''.join(child.itertext()))
    if root.get('data-fit')=='content':
        boxes=[tuple(map(float,e.get('data-bounds').split())) for e in devices if e.get('data-bounds')]
        boxes.extend(box for box,_ in texts)
        boxes.extend((x-4.7,y-4.7,x+4.7,y+4.7) for x,y in dots)
        for line in wires+wireless:
            for a,b in zip(line,line[1:]):boxes.append((min(a[0],b[0])-1.5,min(a[1],b[1])-1.5,max(a[0],b[0])+1.5,max(a[1],b[1])+1.5))
        for e in elements:
            if e.get('data-role')=='region':
                x,y,rw,rh=[float(e.get(k,0)) for k in ('x','y','width','height')];boxes.append((x,y,x+rw,y+rh))
        if boxes:
            left=min(b[0] for b in boxes)-vx;right=vx+w-max(b[2] for b in boxes)
            top=min(b[1] for b in boxes)-vy;bottom=vy+h-max(b[3] for b in boxes)
            if abs(left-right)>1 or abs(top-bottom)>1:r.error('实际内容留白不对称')
    manifests=[e for e in elements if e.get('data-role')=='topology-manifest']
    if manifests:
        try:
            manifest=json.loads(manifests[0].text or '')
            expected={d['id'] for d in manifest['devices']}
            style=manifest.get('style','2.5d')
            if style not in ('2.5d','rounded'):r.error('未知图标风格')
            if any(d.get('data-style','2.5d')!=style for d in devices):r.error('同一张图混用了不同风格')
            actual=[e.get('data-device') for e in devices]
            if set(actual)!=expected or len(actual)!=len(expected):r.error('设备清单与图元不一致')
            if len(wires)+len(wireless)!=len(manifest['links']):r.error('链路数量与输入不一致')
            if len(names)!=len(expected):r.error('设备名称缺失或重复')
            if len(dots)!=2*len(wires):r.error('物理端点数量不正确')
            layout=manifest['layout'];groups=[]
            if layout['type']=='backbone':
                groups=[layout.get('main',[d['id'] for d in manifest['devices']])]
                lower=[name for children in layout.get('bottom',{}).values() for name in children]
                if lower:groups.append(lower)
            elif layout['type']=='aggregation':groups=[list(expected)]
            elif layout['type']=='access':
                groups=[[layout['center']],[name for side in ('left','right','bottom') for name in layout['sides'].get(side,[])]]
            elif layout['type']=='hierarchical':
                level=[layout['root']];seen=set()
                while level:
                    if seen.intersection(level):r.error('分层清单中存在环或重复设备');break
                    seen.update(level)
                    groups.append(level)
                    level=[child for name in level for child in layout.get('children',{}).get(name,[])]
            elif layout['type']=='manual':groups=layout.get('name_groups',[])
            places={e.get('data-device'):e.get('data-placement') for e in names}
            for group in groups:
                if len({places.get(name) for name in group})>1:r.error('同排或同层级设备名的方位不统一')
            visible=[value for _,value in texts]
            for device in manifest['devices']:
                if device.get('ip') and device['ip'] not in visible:r.error('设备 IP 标注缺失：'+device['id'])
            for link in manifest['links']:
                for field in ('from_interface','to_interface','from_ip','to_ip'):
                    value=link.get(field)
                    present=(value in visible) if not field.endswith('_ip') else any(re.search(r'(?<![\w.])'+re.escape(value or '')+r'(?![\d.])',s) for s in visible)
                    if value and not present:r.error('链路标注缺失：'+value)
        except (ValueError,KeyError,TypeError):r.error('拓扑清单 metadata 无效')
    return r


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('files',nargs='*');p.add_argument('--all',action='store_true');p.add_argument('--quiet',action='store_true')
    args=p.parse_args();targets=[(Path(f) if f!='-' else '-',False) for f in args.files]
    if args.all:
        root=Path(__file__).resolve().parents[1]
        targets.extend((f,True) for f in sorted((root/'assets/icons').glob('*.svg')))
        targets.extend((f,True) for f in sorted((root/'assets/styles').glob('*/icons/*.svg')))
        targets.extend((f,False) for f in sorted((root/'examples').glob('*.svg')))
    if not targets:p.print_help();return 0
    errors=warnings=0
    for file,icon in targets:
        try:report=validate(sys.stdin.buffer.read() if file=='-' else file.read_bytes(),icon)
        except (OSError,ValueError) as exc:report=Report();report.error(str(exc))
        for issue in sorted(set(report.errors)):print(f'ERROR {file}: {issue}')
        for issue in sorted(set(report.warnings)):print(f'WARN {file}: {issue}')
        errors+=len(report.errors);warnings+=len(report.warnings)
        if not args.quiet:print(f'{file}: {len(report.errors)} error, {len(report.warnings)} warning')
    if args.quiet:print(f'Checked {len(targets)} SVGs: {errors} errors, {warnings} warnings')
    return int(bool(errors))


if __name__=='__main__':sys.exit(main())
