#!/usr/bin/env python3
"""Render a topology JSON with selectable 2.5D/rounded icons and shared layouts."""
import argparse
import copy
from html import escape
import ipaddress
import json
import math
from pathlib import Path
import re
import sys
import xml.etree.ElementTree as ET

from layout_engine import Drawing, Node, GEOMETRY, normalize_style, text, text_box, line_hits_box

ALIASES={'R':'router','S':'switch-l2','SW':'switch-l2','SW3':'switch-l3',
         'PC':'pc','SERVER':'server','AP':'ap','AC':'ac','FW':'firewall'}


def require(condition,message):
    if not condition:raise ValueError(message)


def validate_spec(raw):
    require(isinstance(raw,dict),'输入应为 JSON 对象')
    spec=copy.deepcopy(raw)
    spec['style']=normalize_style(spec.get('style','2.5d'))
    devices=spec.get('devices');links=spec.setdefault('links',[])
    require(isinstance(devices,list) and devices,'devices 至少有一台设备')
    require(isinstance(links,list),'links 应为数组')
    ids=set()
    for device in devices:
        require(isinstance(device,dict),'每台设备应为对象')
        name=device.get('id','')
        require(isinstance(name,str) and re.fullmatch(r'[\w.:-]+',name),'设备 id 仅使用文字、数字、下划线、点、冒号或连字符')
        require(name not in ids,'设备 id 重复：'+name);ids.add(name)
        kind=ALIASES.get(device.get('kind'),device.get('kind'))
        require(kind in GEOMETRY,'未知图标类型：'+str(kind))
        device['kind']=kind
        for field in ('ip','gateway'):
            if field in device:require(isinstance(device[field],str),f'{name}.{field} 应为文本')
    used_ports=set()
    for index,link in enumerate(links):
        require(isinstance(link,dict),'每条链路应为对象')
        a,b=link.get('from'),link.get('to')
        require(a in ids and b in ids,f'第 {index+1} 条链路引用了不存在的设备')
        require(a!=b,'链路两端不能是同一设备')
        medium=link.setdefault('medium','wired')
        require(medium in ('wired','wireless'),'medium 只能为 wired 或 wireless')
        for end in ('from','to'):
            interface=link.get(end+'_interface','')
            require(isinstance(interface,str),'接口编号应为文本')
            if medium=='wired':
                require(bool(interface),'物理链路两端都应提供真实接口编号')
                port=(link[end],interface)
                require(port not in used_ports,'同一物理接口重复连接：'+':'.join(port))
                used_ports.add(port)
            value=link.get(end+'_ip')
            if value is not None:require(isinstance(value,str),'IP 标注应为文本')
        if 'note' in link:require(isinstance(link['note'],str),'链路 note 应为文本')
        for field in ('from_side','to_side'):
            if field in link:require(link[field] in ('left','right','top','bottom'),'端口方位无效')
        if 'via' in link:
            require(isinstance(link['via'],list) and all(isinstance(p,list) and len(p)==2 and all(isinstance(v,(float,int)) for v in p) for p in link['via']),'via 应为二维坐标数组')
    for obj in devices+links:
        for key,value in obj.items():
            if (key=='ip' or key.endswith('_ip') or key=='gateway') and isinstance(value,str):
                if re.fullmatch(r'\d+\.\d+\.\d+\.\d+(?:/\d+)?',value):
                    try:ipaddress.ip_interface(value)
                    except ValueError as exc:raise ValueError('无效 IP / 前缀：'+value) from exc
    layout=spec.setdefault('layout',{'type':'backbone'})
    if isinstance(layout,str):layout={'type':layout};spec['layout']=layout
    require(isinstance(layout,dict),'layout 应为对象或布局名称')
    require(layout.get('type') in ('backbone','hierarchical','aggregation','access','manual'),'布局类型不受支持')
    require(layout.get('fit','content') in ('content','canvas'),'fit 应为 content 或 canvas')
    require(isinstance(layout.get('padding',64),(int,float)) and layout.get('padding',64)>=32,'padding 至少为 32')
    return spec


def partition(ids,groups):
    flat=[item for group in groups for item in group]
    require(len(flat)==len(set(flat)) and set(flat)==set(ids),'布局分组应覆盖全部设备，每台设备只出现一次')


def create_layout(spec):
    items={device['id']:device for device in spec['devices']}
    ids=list(items);layout=spec['layout'];kind=layout['type']
    nodes={};routes={}
    def node(name,x,y,size=96):
        require(name in items,'布局引用了不存在的设备：'+str(name))
        n=Node(name,items[name]['kind'],x,y,size,style=spec['style'])
        nodes[name]=n
        return n
    if kind=='backbone':
        main=layout.get('main',ids)
        bottom=layout.get('bottom',{})
        require(isinstance(main,list) and main and isinstance(bottom,dict),'backbone 需要 main 数组和可选 bottom 对象')
        require(all(parent in main for parent in bottom),'bottom 的上级设备必须属于 main')
        lower=[item for children in bottom.values() for item in children]
        partition(ids,[main,lower])
        step=float(layout.get('spacing',310))
        require(step>=180,'主干间距过小，建议至少 180')
        for i,name in enumerate(main):node(name,130+i*step,160)
        bottom_step=float(layout.get('bottom_spacing',240))
        for parent,children in bottom.items():
            for i,name in enumerate(children):
                node(name,nodes[parent].x+(i-(len(children)-1)/2)*bottom_step,330)
        min_x=min(n.x for n in nodes.values())
        if min_x<130:
            shift=130-min_x
            for n in nodes.values():n.x+=shift;n.ox+=shift
        width=max(900,max(n.x for n in nodes.values())+130)
        d=Drawing(width,500 if lower else 290)
        d.name_groups=[[nodes[name] for name in main]]
        if lower:d.name_groups.append([nodes[name] for name in lower])
    elif kind=='hierarchical':
        root=layout.get('root');children=layout.get('children',{})
        require(root in items and isinstance(children,dict),'hierarchical 需要 root 和 children')
        parents={};depths={};leaves=[];visiting=set()
        def visit(name,depth):
            require(name in items,'分层布局引用了不存在的设备：'+str(name))
            require(name not in visiting,'分层布局不能有环')
            require(name not in depths,'分层设备不能有多个上级')
            visiting.add(name);depths[name]=depth
            child_list=children.get(name,[])
            require(isinstance(child_list,list),'children 的每项应为设备数组')
            for child in child_list:parents[child]=name;visit(child,depth+1)
            if not child_list:leaves.append(name)
            visiting.remove(name)
        visit(root,0)
        require(set(depths)==set(ids),'分层布局应覆盖全部设备')
        require(set(children)<=set(ids),'children 含不存在的设备')
        edges={frozenset((child,parent)) for child,parent in parents.items()}
        require(len(spec['links'])==len(edges) and {frozenset((l['from'],l['to'])) for l in spec['links']}==edges,'分层连接应与 children 中的真实父子关系一致；网状图用 manual')
        pitch=float(layout.get('leaf_spacing',320));require(pitch>=220,'叶节点间距建议至少 220')
        xs={name:130+i*pitch for i,name in enumerate(leaves)}
        def center(name):
            if name in xs:return xs[name]
            descendants=[]
            def collect(n):
                if not children.get(n):descendants.append(xs[n])
                else:
                    for c in children[n]:collect(c)
            collect(name);xs[name]=(min(descendants)+max(descendants))/2
            for c in children.get(name,[]):center(c)
            return xs[name]
        center(root)
        angles=layout.get('level_angles',[30,45]);require(isinstance(angles,list) and angles,'level_angles 应为角度数组')
        require(all(isinstance(a,(int,float)) and 10<=a<=70 for a in angles),'层间目标角度应在 10–70 度之间')
        ys={0:150.}
        for depth in range(max(depths.values())):
            span=max(abs(xs[c]-xs[p]) for c,p in parents.items() if depths[p]==depth)
            ys[depth+1]=ys[depth]+max(160,span*math.tan(math.radians(angles[min(depth,len(angles)-1)])))
        for name in ids:node(name,xs[name],ys[depths[name]])
        d=Drawing(max(xs.values())+130,max(ys.values())+180)
        d.name_groups=[[nodes[n] for n in ids if depths[n]==depth] for depth in range(max(depths.values())+1)]
        for i,link in enumerate(spec['links']):
            a,b=nodes[link['from']],nodes[link['to']]
            routes[i]=(a.ray_port((b.x,b.y)),b.ray_port((a.x,a.y)),abs(b.y-a.y)>1.4*abs(b.x-a.x))
    elif kind=='aggregation':
        require(len(ids)==2,'aggregation 布局要求恰好两台设备')
        count=len(spec['links'])
        require(count>=1,'链路聚合至少需要一条成员链路')
        require(all(link['medium']=='wired' and {link['from'],link['to']}==set(ids) for link in spec['links']),'聚合成员链路必须连接这两台设备')
        size=max(224,224*(count-1)/3)
        width=max(1500,size*5.4);height=max(500,size+240)
        y=height*.52
        left=node(ids[0],width*.18,y,size)
        right=node(ids[1],width*.82,y,size)
        d=Drawing(width,height);d.name_groups=[[left,right]]
        for i,link in enumerate(spec['links']):
            row=33 if count==1 else 18+30*i/(count-1)
            start=(left.bounds()[2]+16,left.oy+row*left.scale)
            end=(right.bounds()[0]-16,right.oy+row*right.scale)
            routes[i]=(start,end,False) if link['from']==left.name else (end,start,False)
        d.labels.append(text(str(layout.get('bundle','链路聚合')),width/2,150,21,'#344f6b',bold=True))
        d.labels.append(text(f'{count} 条成员链路',width/2,177,14,'#7b8b9c'))
    elif kind=='access':
        center=layout.get('center');sides=layout.get('sides',{})
        require(center in items and isinstance(sides,dict),'access 需要 center 和 sides')
        left,right,bottom=[sides.get(k,[]) for k in ('left','right','bottom')]
        partition(ids,[[center],left,right,bottom])
        require(left or right or bottom,'接入布局至少需要一台外围设备')
        clients=left+right+bottom
        require(len(spec['links'])==len(clients),'每台接入设备应有一条独立链路')
        peers=[]
        for link in spec['links']:
            require(link['medium']=='wired' and center in (link['from'],link['to']),'access 布局只支持中心设备到外围设备的有线连接；其他场景使用 manual')
            peers.append(link['to'] if link['from']==center else link['from'])
        require(set(peers)==set(clients) and len(peers)==len(set(peers)),'接入设备应各连接一次')
        fan=float(layout.get('fan_angle',30));require(10<=fan<=55,'fan_angle 应在 10–55 度之间')
        def angles(count):return [0.] if count==1 else [-fan+2*fan*i/(count-1) for i in range(count)]
        left_angles,right_angles=angles(len(left)),angles(len(right))
        radius=560.
        for group in (left_angles,right_angles):
            if len(group)>1:
                delta=min(math.tan(math.radians(b))-math.tan(math.radians(a)) for a,b in zip(group,group[1:]))
                radius=max(radius,160/delta)
        width=max(2*(radius+190),260*len(bottom)+240)
        radius=width/2-190
        cy=max(390,120+radius*math.tan(math.radians(fan)))
        size=max(224,80*max(len(left)-1,len(right)-1,3),100*max(0,len(bottom)-1))
        switch=node(center,width/2,cy,size)
        for name,angle in zip(left,left_angles):node(name,190,cy+radius*math.tan(math.radians(angle)),112)
        for name,angle in zip(right,right_angles):node(name,width-190,cy+radius*math.tan(math.radians(angle)),112)
        low=max([n.y for n in nodes.values()]+[cy])
        bottom_y=max(low+240,cy+510)
        for i,name in enumerate(bottom):node(name,width/2+(i-(len(bottom)-1)/2)*260,bottom_y,112)
        d=Drawing(width,bottom_y+180 if bottom else low+220)
        d.info_font=17;d.name_groups=[[switch],[nodes[name] for name in clients]]
        for name in clients:
            pc=nodes[name]
            start=switch.ray_port((pc.x,pc.y));end=pc.ray_port((switch.x,switch.y))
            routes[name]=(end,start,False) if name in left else (start,end,name in bottom)
        for i,link in enumerate(spec['links']):
            peer=link['to'] if link['from']==center else link['from']
            start,end,vertical=routes[peer]
            expected_from=peer if peer in left else center
            routes[i]=(start,end,vertical) if link['from']==expected_from else (end,start,vertical)
    else:
        width=layout.get('width',1500);height=layout.get('height',700)
        require(isinstance(width,(int,float)) and width>100 and isinstance(height,(int,float)) and height>100,'manual 需要有效的 width/height')
        for name,item in items.items():
            require(all(isinstance(item.get(k),(int,float)) for k in ('x','y')),'manual 每台设备都需要数值 x/y')
            node(name,item['x'],item['y'],item.get('size',96))
        groups=layout.get('name_groups',[[name] for name in ids])
        partition(ids,groups)
        d=Drawing(width,height);d.name_groups=[[nodes[name] for name in group] for group in groups]
    d.nodes=list(nodes.values())
    d.style=spec['style']
    d.fit_mode=layout.get('fit','content');d.padding=float(layout.get('padding',64))
    for region in layout.get('regions',[]):
        x,y,w,h=[float(region[k]) for k in ('x','y','width','height')]
        d.links.insert(0,f'<rect data-role="region" x="{x:g}" y="{y:g}" width="{w:g}" height="{h:g}" rx="18" fill="#f7f9fc" stroke="#dce4ea" stroke-width="1.3"/>')
        if region.get('label'):d.note(str(region['label']),x+w/2,y+27,size=17)
    return d,nodes,routes


def manual_link(d,a,b,link):
    dx,dy=b.x-a.x,b.y-a.y
    horizontal=abs(dx)>=abs(dy)
    defaults=('right','left') if dx>=0 else ('left','right')
    if not horizontal:defaults=('bottom','top') if dy>=0 else ('top','bottom')
    sides=[link.get('from_side',defaults[0]),link.get('to_side',defaults[1])]
    def point(node,side,offset):
        x1,y1,x2,y2=node.bounds()
        return {'left':(x1-16,node.y+offset),'right':(x2+16,node.y+offset),
                'top':(node.x+offset,y1-16),'bottom':(node.x+offset,y2+16)}[side]
    via=[tuple(p) for p in link.get('via',[])]
    start=(point(a,sides[0],float(link.get('from_offset',0))) if ('from_side' in link or 'from_offset' in link) else a.ray_port(via[0] if via else (b.x,b.y)))
    end=(point(b,sides[1],float(link.get('to_offset',0))) if ('to_side' in link or 'to_offset' in link) else b.ray_port(via[-1] if via else (a.x,a.y)))
    points=[start]+[tuple(p) for p in link.get('via',[])]+[end]
    require(all(p!=q for p,q in zip(points,points[1:])),'链路含重复相邻坐标')
    d.links.append('<polyline data-role="link" points="'+' '.join(f'{x:g},{y:g}' for x,y in points)+'" fill="none" stroke="#626a72" stroke-width="2.3" stroke-linejoin="round"/>')
    d.segments.extend(zip(points,points[1:]))
    for point_,side,label,adjacent in ((start,sides[0],link['from_interface'],points[1]),(end,sides[1],link['to_interface'],points[-2])):
        x,y=point_
        d.dots.append(f'<circle data-role="port" cx="{x:g}" cy="{y:g}" r="4.7" fill="#2b9d48" stroke="#ffffff" stroke-width=".8"/>')
        d.obstacles.append((x-5,y-5,x+5,y+5))
        d.endpoint_label(label,point_,adjacent,abs(adjacent[1]-y)>1.4*abs(adjacent[0]-x))
    for node,field in ((a,'from_ip'),(b,'to_ip')):
        if link.get(field):d.info(node,link[field])


def render_spec(raw,style=None):
    if style is not None:raw=dict(raw,style=style)
    spec=validate_spec(raw)
    d,nodes,routes=create_layout(spec)
    for node in d.nodes:
        x1,y1,x2,y2=node.bounds()
        if d.fit_mode=='canvas':require(x1>=25 and y1>=25 and x2<=d.width-25 and y2<=d.height-25,'设备超出画布，请扩大布局空间：'+node.name)
    for item in spec['devices']:
        n=nodes[item['id']]
        if item.get('ip'):d.info(n,item['ip'])
        if item.get('gateway'):d.info(n,'网关 '+item['gateway'])
        for info in item.get('info',[]):d.info(n,str(info))
    for index,link in enumerate(spec['links']):
        a,b=nodes[link['from']],nodes[link['to']]
        la,lb=link.get('from_interface',''),link.get('to_interface','')
        ia,ib=link.get('from_ip'),link.get('to_ip')
        if link['medium']=='wireless':
            d.wireless(a,b,ib,interface=lb or '无线网卡',caption=str(link.get('caption','无线接入')))
            if la:
                p=a.port('right');d.label(la,p[0]+25,p[1]-15)
            if ia:d.info(a,ia)
        elif index in routes:
            start,end,vertical=routes[index]
            if start[0]>end[0] and not vertical:
                d.direct_link(b,a,end,start,lb,la,False)
            else:d.direct_link(a,b,start,end,la,lb,vertical)
            if ia:d.info(a,(la+' · ' if spec['layout']['type']=='hierarchical' else '')+ia)
            if ib:d.info(b,(lb+' · ' if spec['layout']['type']=='hierarchical' else '')+ib)
        elif spec['layout']['type']=='manual':
            manual_link(d,a,b,link)
        elif a.y==b.y:
            if a.x<b.x:d.cable(a,b,la,lb,ia,ib,note=link.get('note'))
            else:d.cable(b,a,lb,la,ib,ia,note=link.get('note'))
        elif a.x==b.x:
            if a.y<b.y:d.cable(a,b,la,lb,ia,ib,vertical=True)
            else:d.cable(b,a,lb,la,ib,ia,vertical=True)
        else:
            p,q=(a,b) if a.x<b.x else (b,a)
            start=p.ray_port((q.x,q.y));end=q.ray_port((p.x,p.y))
            forward=p is a
            d.direct_link(p,q,start,end,la if forward else lb,lb if forward else la)
            if ia:d.info(a,ia)
            if ib:d.info(b,ib)
        if link.get('note') and (index in routes or a.y!=b.y or spec['layout']['type']=='manual'):
            pa,pb=d.segments[-1]
            d.note(link['note'],(pa[0]+pb[0])/2,(pa[1]+pb[1])/2+34)
        element=ET.fromstring(d.links[-1])
        element.set('data-link',str(index))
        fixed=any(k in link for k in ('from_side','to_side','from_offset','to_offset'))
        routing='parallel' if spec['layout']['type']=='aggregation' else 'fixed' if fixed or link.get('via') else 'radial'
        element.set('data-routing',routing)
        for key in ('from','to','from_interface','to_interface'):
            element.set('data-'+key.replace('_','-'),str(link.get(key,'')))
        d.links[-1]=ET.tostring(element,encoding='unicode')
    svg=d.svg()
    manifest={'format':'net-topo-svg/4','style':spec['style'],'devices':spec['devices'],'links':spec['links'],'layout':spec['layout']}
    insertion='<metadata data-role="topology-manifest">'+escape(json.dumps(manifest,ensure_ascii=False,separators=(',',':')))+'</metadata>'
    svg=svg[:svg.index('>')+1]+insertion+svg[svg.index('>')+1:]
    return svg.encode('utf-8')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input',nargs='?',help='JSON 文件，或 - 从 stdin 读取')
    parser.add_argument('-o','--output',help='可选输出 SVG 路径；默认写 stdout')
    parser.add_argument('--list-icons',action='store_true')
    parser.add_argument('--strict',action='store_true',help='有检查警告时也停止输出')
    parser.add_argument('--style',help='整图风格：2.5d 或 rounded；覆盖输入 JSON 的 style')
    args=parser.parse_args()
    if args.list_icons:
        print(json.dumps(sorted(GEOMETRY),ensure_ascii=False,indent=2));return 0
    if not args.input:parser.print_help();return 0
    try:
        source=sys.stdin.read() if args.input=='-' else Path(args.input).read_text(encoding='utf-8')
        result=render_spec(json.loads(source),style=args.style)
        from check_topology import validate
        report=validate(result)
        if report.errors or (args.strict and report.warnings):
            raise ValueError('；'.join(report.errors+report.warnings))
        for issue in report.warnings:print('WARN '+issue,file=sys.stderr)
        if args.output:Path(args.output).write_bytes(result)
        else:sys.stdout.buffer.write(result)
        return 0
    except (ValueError,KeyError,TypeError,OSError) as exc:
        print('绘图失败：'+str(exc),file=sys.stderr);return 2


if __name__=='__main__':sys.exit(main())
