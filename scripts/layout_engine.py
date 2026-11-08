"""Reusable SVG primitives. Python standard library only; no file writes."""
from pathlib import Path
from html import escape
import json
import hashlib
import math
import re
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[1]
ICONS=ROOT/'assets/icons'
GEOMETRY=json.loads((ROOT/'assets/geometry.json').read_text(encoding='utf-8'))
STYLE_GEOMETRY={'2.5d':GEOMETRY,'rounded':json.loads((ROOT/'assets/styles/rounded/geometry.json').read_text(encoding='utf-8'))}
STYLE_ICONS={'2.5d':ICONS,'rounded':ROOT/'assets/styles/rounded/icons'}
ANCHORS={k:v['anchors'] for k,v in GEOMETRY.items()}
BOUNDS={k:v['bounds'] for k,v in GEOMETRY.items()}


def normalize_style(value):
    aliases={'2.5d':'2.5d','isometric':'2.5d','立体':'2.5d','rounded':'rounded','tile':'rounded','圆角':'rounded','圆角色块':'rounded'}
    if not isinstance(value,str) or value.strip().lower() not in aliases:raise ValueError('style 应为 2.5d 或 rounded（圆角）')
    return aliases[value.strip().lower()]

def text(value,x,y,size=16,color='#35424c',anchor='middle',bold=False):
    return f'<text x="{x:g}" y="{y:g}" font-size="{size}" font-weight="{600 if bold else 400}" fill="{color}" text-anchor="{anchor}">{escape(value)}</text>'


def text_box(value,x,y,size=16,anchor='middle'):
    width=sum(1 if ord(c)>255 else .58 for c in value)*size
    left=x-width/2 if anchor=='middle' else x-width if anchor=='end' else x
    return left,y-size*.85,left+width,y+size*.25


def overlaps(a,b,pad=4):
    return min(a[2],b[2])+pad>max(a[0],b[0]) and min(a[3],b[3])+pad>max(a[1],b[1])


def line_hits_box(start,end,box,pad=6):
    # Segment/rectangle clipping also handles direct diagonal cables.
    x0,y0=start;x1,y1=end
    lo_x,lo_y,hi_x,hi_y=box[0]-pad,box[1]-pad,box[2]+pad,box[3]+pad
    t0,t1=0.,1.
    dx,dy=x1-x0,y1-y0
    for p,q in ((-dx,x0-lo_x),(dx,hi_x-x0),(-dy,y0-lo_y),(dy,hi_y-y0)):
        if abs(p)<1e-9:
            if q<0:return False
        else:
            r=q/p
            if p<0:t0=max(t0,r)
            else:t1=min(t1,r)
            if t0>t1:return False
    return True


class Node:
    def __init__(self,name,kind,x,y,size=96,style='2.5d'):
        self.name,self.kind,self.x,self.y,self.size=name,kind,x,y,size
        self.style=normalize_style(style)
        self.geometry=STYLE_GEOMETRY[self.style][kind]
        self.scale=size/64
        self.ox=x-32*self.scale
        self.oy=y-self.geometry['anchors']['belt']*self.scale

    def port(self,side):
        x,y=self.geometry['anchors'][side]
        return self.ox+x*self.scale,self.oy+y*self.scale

    def ray_port(self,toward,gap=16):
        dx,dy=toward[0]-self.x,toward[1]-self.y
        length=math.hypot(dx,dy)
        if length<1e-6:raise ValueError('不能连接位置重合的设备')
        ux,uy=dx/length,dy/length
        hull=self.geometry.get('visible_hull')
        if not hull:
            x1,y1,x2,y2=self.bounds()
            polygon=[(x1,y1),(x2,y1),(x2,y2),(x1,y2)]
        else:polygon=[(self.ox+x*self.scale,self.oy+y*self.scale) for x,y in hull]
        cross=lambda a,b:a[0]*b[1]-a[1]*b[0]
        hits=[]
        for p,q in zip(polygon,polygon[1:]+polygon[:1]):
            edge=(q[0]-p[0],q[1]-p[1]);den=cross((ux,uy),edge)
            if abs(den)<1e-9:continue
            delta=(p[0]-self.x,p[1]-self.y)
            distance=cross(delta,edge)/den;fraction=cross(delta,(ux,uy))/den
            if distance>=0 and -.0001<=fraction<=1.0001:hits.append(distance)
        if not hits:raise ValueError('无法计算设备轮廓接点：'+self.name)
        distance=max(hits)+gap
        return self.x+ux*distance,self.y+uy*distance

    def bounds(self):
        x1,y1,x2,y2=self.geometry['bounds']
        return self.ox+x1*self.scale,self.oy+y1*self.scale,self.ox+x2*self.scale,self.oy+y2*self.scale

    def intersects_box(self,box,pad=2):
        hull=self.geometry.get('visible_hull')
        if not hull:return overlaps(box,self.bounds(),pad)
        polygon=[(self.ox+x*self.scale,self.oy+y*self.scale) for x,y in hull]
        if any(line_hits_box(a,b,box,pad) for a,b in zip(polygon,polygon[1:]+polygon[:1])):return True
        for x,y in ((box[0],box[1]),(box[2],box[1]),(box[2],box[3]),(box[0],box[3])):
            signs=[(b[0]-a[0])*(y-a[1])-(b[1]-a[1])*(x-a[0]) for a,b in zip(polygon,polygon[1:]+polygon[:1])]
            if all(s>=0 for s in signs) or all(s<=0 for s in signs):return True
        return False

    def art(self):
        source=(STYLE_ICONS[self.style]/f'{self.kind}.svg').read_text(encoding='utf-8')
        inner=source[source.index('>')+1:source.rindex('</svg>')]
        inner=re.sub(r'<(title|desc)>.*?</\1>','',inner)
        if 'id=' in inner:
            wrapper=ET.fromstring('<svg xmlns="http://www.w3.org/2000/svg">'+inner+'</svg>')
            prefix='device-'+hashlib.sha256(self.name.encode('utf-8')).hexdigest()[:16]+'-'
            ids={e.get('id'):prefix+e.get('id') for e in wrapper.iter() if e.get('id')}
            for element in wrapper.iter():
                if element.get('id'):element.set('id',ids[element.get('id')])
                for attr,value in list(element.attrib.items()):
                    if attr.rsplit('}',1)[-1]=='href' and value.startswith('#') and value[1:] in ids:value='#'+ids[value[1:]]
                    value=re.sub(r'url\(\s*#([^\s)]+)\s*\)',lambda m:'url(#'+ids.get(m[1],m[1])+')',value)
                    element.set(attr,value)
            ET.register_namespace('','http://www.w3.org/2000/svg')
            inner=''.join(ET.tostring(child,encoding='unicode') for child in wrapper)
        bounds=' '.join(f'{v:g}' for v in self.bounds())
        return f'<g data-role="device" data-device="{self.name}" data-kind="{self.kind}" data-style="{self.style}" data-center="{self.x:g} {self.y:g}" data-bounds="{bounds}" transform="translate({self.ox:g} {self.oy:g}) scale({self.scale:g})">{inner}</g>'


class Drawing:
    def __init__(self,width,height):
        self.width,self.height=width,height
        self.links=[];self.dots=[];self.labels=[];self.nodes=[]
        self.obstacles=[];self.segments=[];self.information={}
        self.name_placements={}
        self.name_groups=[]
        self.annotations=[]
        self.info_font=14
        self.pending_interfaces=[]
        self.fit_mode='content'
        self.padding=64
        self.style='2.5d'

    def info(self,node,value):
        self.information.setdefault(node.name,[]).append(value)

    def label(self,interface,x,y,anchor='start',endpoint=None):
        binding='' if endpoint is None else f' data-endpoint="{endpoint[0]:g} {endpoint[1]:g}"'
        out=f'<g data-role="port-label"{binding}>'+text(interface,x,y,15,'#35424c',anchor,True)
        self.labels.append(out+'</g>')
        self.obstacles.append(text_box(interface,x,y,15,anchor))

    def endpoint_label(self,value,point,neighbor,vertical=False):
        if value:self.pending_interfaces.append((str(value),point,neighbor,vertical))

    def place_interfaces(self):
        requests=sorted(self.pending_interfaces,key=lambda r:(r[1][1],r[1][0],r[0]))
        domains=[]
        for value,point,neighbor,vertical in requests:
            px,py=point;dx,dy=neighbor[0]-px,neighbor[1]-py
            length=math.hypot(dx,dy)
            if length<1e-6:raise ValueError('接口所属线段长度为零')
            ux,uy=dx/length,dy/length
            width=sum(1 if ord(c)>255 else .58 for c in value)*15;height=16.5
            steep=vertical or abs(dy)>1.4*abs(dx)
            candidates=[]
            if abs(dy)<.001:
                candidates.append((px+9 if dx>0 else px-9,py-15,'start' if dx>0 else 'end',-6))
            elif steep:candidates.append((px+13,py+5,'start',-5))
            if abs(dy)>.001:
                for x,anchor in ((px+13,'start'),(px-13,'end')):
                    for offset in (-30,-22,-14,-6,6,14,22,30):
                        candidates.append((x,py+offset,anchor,1 if (steep and anchor=='start') else 3))
            # Horizontal text gets a constant perpendicular clearance from
            # diagonal lines. Tangential candidates keep it close to the dot.
            nx,ny=-uy,ux
            if (steep and nx<0) or (not steep and ny>0):nx,ny=-nx,-ny
            tangent=abs(ux)*width/2+abs(uy)*height/2
            support=abs(nx)*width/2+abs(ny)*height/2
            for extra in (0,14,28):
                for sign in (1,-1):
                    for shift in (0,tangent+9,-tangent-9,tangent*.5,-tangent*.5):
                        cx=px+ux*shift+nx*sign*(support+10+extra)
                        cy=py+uy*shift+ny*sign*(support+10+extra)
                        candidates.append((cx,cy+4.5,'middle',2+(sign<0)*2+extra*.2))
            valid=[]
            for x,y,anchor,penalty in candidates:
                box=text_box(value,x,y,15,anchor)
                if self.fit_mode=='canvas' and (box[0]<30 or box[1]<30 or box[2]>self.width-30 or box[3]>self.height-30):continue
                if any(overlaps(box,b,pad=3) for b in self.obstacles):continue
                if any(n.intersects_box(box,pad=2) for n in self.nodes):continue
                if any(line_hits_box(a,b,box,pad=3) for a,b in self.segments):continue
                distance=math.hypot(max(box[0]-px,0,px-box[2]),max(box[1]-py,0,py-box[3]))
                center_distance=math.hypot((box[0]+box[2])/2-px,(box[1]+box[3])/2-py)
                valid.append((distance+.06*center_distance+penalty,x,y,anchor,box))
            if not valid:raise ValueError('接口文字没有空位，请增加同层间距：'+value)
            unique={tuple(round(v,3) for v in c[4]):c for c in sorted(valid,key=lambda r:-r[0])}
            domains.append(sorted(unique.values(),key=lambda r:r[0])[:24])
        assigned={};attempts=[0]
        def solve(remaining):
            if not remaining:return True
            attempts[0]+=1
            if attempts[0]>20000:return False
            available={i:[c for c in domains[i] if not any(overlaps(c[4],a[4],pad=3) for a in assigned.values())] for i in remaining}
            index=min(remaining,key=lambda i:(len(available[i]),i))
            for candidate in available[index]:
                assigned[index]=candidate
                if solve([i for i in remaining if i!=index]):return True
                del assigned[index]
            return False
        if not solve(list(range(len(requests)))):raise ValueError('接口标注相互拥挤，请增加同层间距或设备尺寸')
        for i,(value,*_) in enumerate(requests):
            _,x,y,anchor,_=assigned[i]
            self.label(value,x,y,anchor,endpoint=requests[i][1])
        self.pending_interfaces=[]

    def cable(self,a,b,a_label,b_label,a_ip=None,b_ip=None,vertical=False,note=None,local_y=None):
        if local_y is not None:
            # Parallel member links share aligned endpoint columns.
            start=(a.bounds()[2],a.oy+local_y*a.scale)
            end=(b.bounds()[0],b.oy+local_y*b.scale)
        else:
            start=a.ray_port((b.x,b.y))
            end=b.ray_port((a.x,a.y))
        if local_y is not None:
            start=(start[0]+16,start[1]);end=(end[0]-16,end[1])
        self.direct_link(a,b,start,end,a_label,b_label,vertical)
        if vertical:
            # Supplemental data belongs in a separate lane/device information
            # area; it never changes the endpoint label coordinates.
            if a_ip:self.note(a_ip,start[0]+13,start[1]+31,anchor='start')
            if b_ip:self.info(b,b_ip)
        else:
            line_y=start[1]
            label_y=line_y-15
            left_x=start[0]+9
            right_x=end[0]-9
            if a_ip:self.note(a_ip,left_x,line_y+34,anchor='start')
            if b_ip:self.note(b_ip,right_x,end[1]+34,anchor='end')
            if note:self.note(note,(start[0]+end[0])/2,line_y+34)

    def wireless(self,a,b,ip=None,interface='无线网卡',caption='无线接入'):
        x1,y1=a.ray_port((b.x,b.y));x2,y2=b.ray_port((a.x,a.y))
        self.links.append(f'<path data-role="wireless-link" d="M{x1:g} {y1:g} L{x2:g} {y2:g}" fill="none" stroke="#9c86c7" stroke-width="2.1" stroke-dasharray="7 7"/>')
        self.segments.append(((x1,y1),(x2,y2)))
        self.labels.append(text(caption,(x1+x2)/2,y1-16,14,'#8c75b5'))
        self.obstacles.append(text_box(caption,(x1+x2)/2,y1-16,14))
        if interface:self.endpoint_label(interface,(x2,y2),(x1,y1))
        if ip:
            self.info(b,ip)

    def direct_link(self,a,b,start,end,start_label,end_label,vertical_labels=False):
        self.links.append(f'<polyline data-role="link" data-from="{a.name}" data-to="{b.name}" points="{start[0]:g},{start[1]:g} {end[0]:g},{end[1]:g}" fill="none" stroke="#626a72" stroke-width="2.3"/>')
        self.segments.append((start,end))
        for x,y in (start,end):
            self.dots.append(f'<circle data-role="port" cx="{x:g}" cy="{y:g}" r="4.7" fill="#2b9d48" stroke="#ffffff" stroke-width=".8"/>')
            self.obstacles.append((x-5,y-5,x+5,y+5))
        if vertical_labels:
            self.endpoint_label(start_label,start,end,True)
            self.endpoint_label(end_label,end,start,True)
        else:
            self.endpoint_label(start_label,start,end)
            self.endpoint_label(end_label,end,start)

    def place_names(self):
        if self.name_placements:return
        occupied=list(self.obstacles)
        groups=self.name_groups or [self.nodes]
        def candidate_box(node,direction,group):
            x1,y1,x2,y2=node.bounds()
            width=sum(1 if ord(c)>255 else .58 for c in node.name)*20
            height=22;gap=16;diagonal=gap/math.sqrt(2)
            cx,cy=(x1+x2)/2,(y1+y2)/2
            # A row/layer shares a label band, so names align as a group.
            aligned_row=max(n.y for n in group)-min(n.y for n in group)<1
            row_top=min(n.bounds()[1] for n in group) if aligned_row else y1
            row_bottom=max(n.bounds()[3] for n in group) if aligned_row else y2
            positions={
                'S':(cx-width/2,row_bottom+gap),
                'N':(cx-width/2,row_top-gap-height),
                'E':(x2+gap,cy-height/2),
                'W':(x1-gap-width,cy-height/2),
                'SE':(x2+diagonal,y2+diagonal),
                'SW':(x1-diagonal-width,y2+diagonal),
                'NE':(x2+diagonal,y1-diagonal-height),
                'NW':(x1-diagonal-width,y1-diagonal-height),
            }
            left,top_y=positions[direction]
            return left,top_y,left+width,top_y+height
        def valid(node,box,extra):
            if self.fit_mode=='canvas' and (box[0]<35 or box[1]<35 or box[2]>self.width-35 or box[3]>self.height-35):return False
            if any(overlaps(box,o) for o in occupied+extra):return False
            if any(overlaps(box,other.bounds()) for other in self.nodes if other is not node):return False
            if any(line_hits_box(a,b,box) for a,b in self.segments):return False
            return True
        for group in groups:
            chosen=None
            for direction in ('S','N','E','W','SE','SW','NE','NW'):
                boxes=[]
                for node in group:
                    box=candidate_box(node,direction,group)
                    if not valid(node,box,boxes):break
                    boxes.append(box)
                if len(boxes)==len(group):
                    chosen=(direction,boxes)
                    break
            if chosen is None:
                raise ValueError('同组设备无法统一命名方位；应增加空间，不能为名称绕线')
            direction,boxes=chosen
            for node,box in zip(group,boxes):
                left,top_y,right,_=box
                self.name_placements[node.name]=(direction,box)
                occupied.append(box)
                self.labels.append(f'<g data-role="device-name" data-device="{node.name}" data-placement="{direction}">'+text(node.name,(left+right)/2,top_y+17,20,'#151c22',bold=True)+'</g>')
        # Device metadata follows the chosen name, without displacing ports.
        for node in self.nodes:
            if node.name not in self.information:continue
            direction,box=self.name_placements[node.name]
            y=box[3]+23 if direction=='S' else node.bounds()[3]+36
            info=[]
            for value in self.information[node.name]:
                self.note(value,node.x,y,size=self.info_font,device=node.name)
                y+=max(22,self.info_font+7)


    def note(self,value,x,y,size=14,anchor='middle',device=''):
        self.annotations.append((str(value),x,y,size,anchor,device))

    def place_annotations(self):
        occupied=list(self.obstacles)+[v[1] for v in self.name_placements.values()]
        for value,x,y,size,anchor,device in self.annotations:
            for offset in (0,22,44,-22,66,88,-44,110,132):
                box=text_box(value,x,y+offset,size,anchor)
                if self.fit_mode=='canvas' and (box[0]<30 or box[1]<30 or box[2]>self.width-30 or box[3]>self.height-30):continue
                if any(overlaps(box,b,pad=3) for b in occupied):continue
                if any(overlaps(box,n.bounds(),pad=3) for n in self.nodes):continue
                if any(line_hits_box(a,b,box,pad=3) for a,b in self.segments):continue
                self.labels.append(f'<g data-role="annotation" data-device="{escape(device,quote=True)}">'+text(value,x,y+offset,size,'#6c7887',anchor)+'</g>')
                occupied.append(box)
                break
            else:
                raise ValueError('补充信息没有空位，请扩大画布或间距；不要移动接口编号：'+value)
        self.annotations=[]

    def content_bounds(self):
        boxes=[n.bounds() for n in self.nodes]
        for markup in self.labels:
            for e in ET.fromstring(markup).iter():
                if e.tag.rsplit('}',1)[-1]=='text':
                    boxes.append(text_box(''.join(e.itertext()),float(e.get('x',0)),float(e.get('y',0)),float(e.get('font-size',16)),e.get('text-anchor','start')))
        for markup in self.links:
            e=ET.fromstring(markup)
            if e.get('data-role')=='region':
                x,y,w,h=[float(e.get(k,0)) for k in ('x','y','width','height')];boxes.append((x,y,x+w,y+h))
        for markup in self.dots:
            e=ET.fromstring(markup);x,y,r=[float(e.get(k,0)) for k in ('cx','cy','r')];boxes.append((x-r,y-r,x+r,y+r))
        for a,b in self.segments:boxes.append((min(a[0],b[0])-1.5,min(a[1],b[1])-1.5,max(a[0],b[0])+1.5,max(a[1],b[1])+1.5))
        return min(b[0] for b in boxes),min(b[1] for b in boxes),max(b[2] for b in boxes),max(b[3] for b in boxes)

    def svg(self):
        self.place_interfaces()
        self.place_names()
        self.place_annotations()
        bounds=self.content_bounds()
        if self.fit_mode=='content':
            width=math.ceil(max(200,bounds[2]-bounds[0]+2*self.padding))
            height=math.ceil(max(180,bounds[3]-bounds[1]+2*self.padding))
            vx=(bounds[0]+bounds[2]-width)/2;vy=(bounds[1]+bounds[3]-height)/2
        else:vx=vy=0;width=self.width;height=self.height
        extent=' '.join(f'{v:.6f}' for v in bounds)
        head=(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{vx:.6f} {vy:.6f} {width:g} {height:g}" width="{width:g}" height="{height:g}" data-style="{self.style}" data-fit="{self.fit_mode}" data-content-bounds="{extent}" font-family="Arial, PingFang SC, Microsoft YaHei, sans-serif">'
              '<title>网络拓扑样式预览</title><desc>沿用 Ops 横向主干与简洁标注的独立设计稿</desc>'
              f'<rect x="{vx:.6f}" y="{vy:.6f}" width="100%" height="100%" fill="#ffffff"/>'
              f'<rect x="{vx+20:.6f}" y="{vy+20:.6f}" width="{width-40:g}" height="{height-40:g}" rx="18" fill="#fbfcfd" stroke="#dce4ea" stroke-width="1.5"/>')
        return head+''.join(self.links)+''.join(n.art() for n in self.nodes)+''.join(self.dots)+''.join(self.labels)+'</svg>'


