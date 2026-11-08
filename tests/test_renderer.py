"""Behavioral checks for portable, model-independent SVG generation."""
import copy
import json
import math
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from topology import render_spec, validate_spec
from check_topology import validate


def spec(name):return json.loads((ROOT/'examples'/f'{name}.json').read_text())
def role(root,name):return [e for e in root.iter() if e.get('data-role')==name]
def view(data):return ET.fromstring(data)


class RendererTests(unittest.TestCase):
    def test_approved_examples_are_reproducible_and_clean(self):
        for name in ('basic-access','link-aggregation','multi-access','hierarchical-access'):
            with self.subTest(name=name):
                result=render_spec(spec(name))
                self.assertEqual(result,render_spec(spec(name)))
                self.assertEqual(result,(ROOT/'examples'/f'{name}.svg').read_bytes())
                report=validate(result)
                self.assertEqual(report.errors,[])
                self.assertEqual(report.warnings,[])

    def test_optional_metadata_does_not_reposition_ports_or_names(self):
        original=spec('basic-access');plain=copy.deepcopy(original)
        for device in plain['devices']:
            for field in ('ip','gateway','info'):device.pop(field,None)
        for link in plain['links']:
            for field in ('from_ip','to_ip','note'):link.pop(field,None)
        a,b=view(render_spec(original)),view(render_spec(plain))
        for name in ('link','wireless-link','port','port-label','device-name'):
            self.assertEqual([ET.tostring(e) for e in role(a,name)],[ET.tostring(e) for e in role(b,name)])

    def test_aggregation_generalizes_to_six_members(self):
        data=spec('link-aggregation')
        data['links']=[dict(data['links'][0],from_interface=f'GE0/0/{i}',to_interface=f'GE0/0/{i}') for i in range(1,7)]
        root=view(render_spec(data))
        self.assertEqual(len(role(root,'link')),6)
        self.assertEqual(len(role(root,'port')),12)
        self.assertEqual({e.get('data-placement') for e in role(root,'device-name')},{'S'})
        self.assertEqual(validate(ET.tostring(root)).errors,[])

    def test_access_generalizes_to_different_names_counts_and_ips(self):
        data=spec('multi-access');remove={'PC3','PC7','PC9'}
        data['devices']=[d for d in data['devices'] if d['id'] not in remove]
        data['links']=[l for l in data['links'] if l['from'] not in remove and l['to'] not in remove]
        for side,values in data['layout']['sides'].items():data['layout']['sides'][side]=[v for v in values if v not in remove]
        for device in data['devices']:
            if device['id']=='LSW1':device['id']='Access-SW'
            elif device.get('ip'):device['ip']=device['ip'].replace('192.168.10.','10.20.30.')
        data['layout']['center']='Access-SW'
        for link in data['links']:
            for field in ('from','to'):
                if link[field]=='LSW1':link[field]='Access-SW'
        root=view(render_spec(data))
        self.assertEqual(len(role(root,'device')),7)
        self.assertEqual(len(role(root,'link')),6)
        self.assertEqual(len(role(root,'annotation')),6)
        self.assertEqual(validate(ET.tostring(root)).errors,[])

    def test_nine_clients_keep_distinct_links_and_ip_labels(self):
        root=view(render_spec(spec('multi-access')))
        self.assertEqual(len(role(root,'device')),10)
        self.assertEqual(len(role(root,'link')),9)
        self.assertEqual(len(role(root,'port')),18)
        values=[''.join(e.itertext()) for e in role(root,'annotation')]
        self.assertEqual(set(values),{f'192.168.10.{i}/24' for i in range(11,20)})

    def test_duplicate_physical_port_is_rejected(self):
        data=spec('link-aggregation')
        data['links'][1]['from_interface']=data['links'][0]['from_interface']
        with self.assertRaisesRegex(ValueError,'重复连接'):validate_spec(data)

    def test_unknown_device_is_rejected(self):
        data=spec('basic-access');data['links'][0]['to']='missing'
        with self.assertRaisesRegex(ValueError,'不存在'):validate_spec(data)

    def test_all_32_icons_can_be_used_without_redrawing(self):
        geometry=json.loads((ROOT/'assets/geometry.json').read_text())
        self.assertEqual(len(geometry),32)
        for kind in geometry:
            with self.subTest(kind=kind):
                root=view(render_spec({'layout':{'type':'manual','width':450,'height':430},'devices':[{'id':'Device1','kind':kind,'x':225,'y':180}],'links':[]}))
                self.assertEqual(len(role(root,'device')),1)
                self.assertEqual(validate(ET.tostring(root)).errors,[])

    def test_manual_can_use_a_direct_diagonal_or_explicit_bend(self):
        data={'layout':{'type':'manual','width':800,'height':600,'name_groups':[['R1','R2']]},'devices':[{'id':'R1','kind':'router','x':180,'y':180},{'id':'R2','kind':'router','x':620,'y':390}],'links':[{'from':'R1','to':'R2','from_interface':'GE0/0/1','to_interface':'GE0/0/1'}]}
        root=view(render_spec(data));self.assertEqual(len(role(root,'link')[0].get('points').split()),2)
        self.assertEqual(validate(ET.tostring(root)).errors,[])
        data['links'][0]['via']=[[400,180],[400,390]]
        root=view(render_spec(data));self.assertEqual(len(role(root,'link')[0].get('points').split()),4)

    def test_package_runs_from_an_unrelated_directory_without_cos_or_tmp(self):
        with tempfile.TemporaryDirectory() as folder:
            target=Path(folder)/'portable-skill'
            shutil.copytree(ROOT,target,ignore=shutil.ignore_patterns('__pycache__'))
            result=subprocess.run([sys.executable,'-B',str(target/'scripts/topology.py'),str(target/'examples/link-aggregation.json'),'--strict'],cwd=folder,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
            self.assertEqual(result.returncode,0,result.stderr.decode())
            self.assertEqual(result.stdout,(ROOT/'examples/link-aggregation.svg').read_bytes())

    def test_short_backbone_has_no_one_sided_minimum_canvas_gap(self):
        data={'layout':'backbone','devices':[{'id':'R1','kind':'router'},{'id':'PC1','kind':'pc'}],'links':[{'from':'R1','to':'PC1','from_interface':'GE0/0/0','to_interface':'E0/0/1'}]}
        root=view(render_spec(data));vx,vy,w,h=map(float,root.get('viewBox').split())
        x1,y1,x2,y2=map(float,root.get('data-content-bounds').split())
        self.assertLess(w,900)
        self.assertAlmostEqual(x1-vx,vx+w-x2,places=4)
        self.assertAlmostEqual(y1-vy,vy+h-y2,places=4)

    def test_manual_off_center_content_is_fitted_without_moving_nodes(self):
        data={'layout':{'type':'manual','width':1800,'height':800},'devices':[{'id':'R1','kind':'router','x':950,'y':300},{'id':'PC1','kind':'pc','x':1350,'y':450,'ip':'192.168.100.100/24'}],'links':[{'from':'R1','to':'PC1','from_interface':'GE0/0/1','to_interface':'E0/0/1'}]}
        root=view(render_spec(data));vx,vy,w,h=map(float,root.get('viewBox').split())
        x1,y1,x2,y2=map(float,root.get('data-content-bounds').split())
        self.assertAlmostEqual(x1-vx,vx+w-x2,places=4)
        centers={e.get('data-device'):e.get('data-center') for e in role(root,'device')}
        self.assertEqual(centers['R1'],'950 300')
        self.assertEqual(validate(ET.tostring(root)).errors,[])

    def test_diagonal_endpoints_follow_the_device_center_direction(self):
        root=view(render_spec(spec('hierarchical-access')))
        centers={e.get('data-device'):tuple(map(float,e.get('data-center').split())) for e in role(root,'device')}
        for line in role(root,'link'):
            a,b=[tuple(map(float,p.split(','))) for p in line.get('points').split()]
            for owner in (line.get('data-from'),line.get('data-to')):
                x,y=centers[owner]
                distance=abs((b[0]-a[0])*(y-a[1])-(b[1]-a[1])*(x-a[0]))/math.dist(a,b)
                # SVG coordinates are serialized to six significant digits.
                self.assertLess(distance,.01)

    def test_hierarchical_siblings_have_mirrored_30_and_45_degree_links(self):
        root=view(render_spec(spec('hierarchical-access')))
        c={e.get('data-device'):tuple(map(float,e.get('data-center').split())) for e in role(root,'device')}
        self.assertAlmostEqual((c['LSW1'][0]+c['LSW2'][0])/2,c['R1'][0])
        self.assertAlmostEqual((c['PC1'][0]+c['PC2'][0])/2,c['LSW1'][0])
        for parent,child,expected in [('R1','LSW1',30),('R1','LSW2',30),('LSW1','PC1',45),('LSW2','PC4',45)]:
            angle=math.degrees(math.atan2(abs(c[parent][1]-c[child][1]),abs(c[parent][0]-c[child][0])))
            self.assertAlmostEqual(angle,expected,places=3)

    def test_unequal_access_counts_share_mirrored_outer_angles(self):
        root=view(render_spec(spec('multi-access')))
        c={e.get('data-device'):tuple(map(float,e.get('data-center').split())) for e in role(root,'device')}
        for a,b in [('PC1','PC4'),('PC3','PC7')]:
            self.assertAlmostEqual(c[a][1],c[b][1],places=3)
            self.assertAlmostEqual(c['LSW1'][0]-c[a][0],c[b][0]-c['LSW1'][0],places=3)

    def test_diagonal_interface_labels_stay_near_their_own_endpoint(self):
        for name in ('multi-access','hierarchical-access'):
            root=view(render_spec(spec(name)))
            for group in role(root,'port-label'):
                self.assertIsNotNone(group.get('data-endpoint'))
                px,py=map(float,group.get('data-endpoint').split());t=next(iter(group))
                # Compare point with the full horizontal label rectangle.
                x,y=float(t.get('x')),float(t.get('y'));width=len(t.text)*15*.58
                anchor=t.get('text-anchor');left=x-width/2 if anchor=='middle' else x-width if anchor=='end' else x
                distance=math.hypot(max(left-px,0,px-left-width),max(y-12.75-py,0,py-y-3.75))
                self.assertLess(distance,64)

    def test_hierarchical_rejects_non_tree_connections(self):
        data=spec('hierarchical-access');data['layout']['children']['LSW1'].append('LSW2')
        with self.assertRaisesRegex(ValueError,'多个上级|有环'):render_spec(data)

    def test_explicit_canvas_mode_is_available_for_fixed_size_exports(self):
        data=spec('link-aggregation');data['layout']['fit']='canvas'
        root=view(render_spec(data))
        self.assertEqual(root.get('viewBox'),'0.000000 0.000000 1500 500')

    def test_rounded_examples_use_the_same_graph_and_pass_checks(self):
        for name in ('basic-access','link-aggregation','multi-access','hierarchical-access'):
            with self.subTest(name=name):
                rounded=render_spec(spec(name),style='rounded')
                self.assertEqual(rounded,(ROOT/'examples'/f'{name}-rounded.svg').read_bytes())
                root=view(rounded)
                self.assertEqual(root.get('data-style'),'rounded')
                self.assertEqual({n.get('data-style') for n in role(root,'device')},{'rounded'})
                report=validate(rounded)
                self.assertEqual(report.errors,[]);self.assertEqual(report.warnings,[])
                base=view(render_spec(spec(name)))
                for role_name in ('device','link','wireless-link','port','port-label','device-name','annotation'):
                    self.assertEqual(len(role(root,role_name)),len(role(base,role_name)))

    def test_rounded_has_all_32_matching_device_types(self):
        base=json.loads((ROOT/'assets/geometry.json').read_text())
        rounded=json.loads((ROOT/'assets/styles/rounded/geometry.json').read_text())
        self.assertEqual(set(base),set(rounded))
        for kind in rounded:
            result=render_spec({'style':'rounded','layout':{'type':'manual','width':450,'height':430},'devices':[{'id':'Device1','kind':kind,'x':225,'y':180}],'links':[]})
            self.assertEqual(validate(result).errors,[])

    def test_repeated_rounded_icons_have_unique_internal_gradient_ids(self):
        root=view(render_spec(spec('multi-access'),style='rounded'))
        ids=[e.get('id') for e in root.iter() if e.get('id')]
        self.assertEqual(len(ids),len(set(ids)))
        self.assertEqual(len(ids),20)
        self.assertTrue(any(e.tag.endswith('linearGradient') for e in root.iter()))

    def test_style_switch_has_no_global_state_and_keeps_2p5d_default(self):
        data=spec('hierarchical-access')
        before=render_spec(data)
        self.assertEqual(view(before).get('data-style'),'2.5d')
        render_spec(data,style='rounded')
        self.assertEqual(render_spec(data),before)
        self.assertEqual(render_spec(dict(data,style='圆角')),render_spec(data,style='rounded'))

    def test_cli_style_overrides_the_json_selection(self):
        result=subprocess.run([sys.executable,'-B',str(ROOT/'scripts/topology.py'),str(ROOT/'examples/basic-access.json'),'--style','rounded','--strict'],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        self.assertEqual(result.returncode,0,result.stderr.decode())
        self.assertEqual(result.stdout,(ROOT/'examples/basic-access-rounded.svg').read_bytes())

    def test_invalid_style_fails_clearly(self):
        with self.assertRaisesRegex(ValueError,'style'):render_spec(dict(spec('basic-access'),style='unknown'))


if __name__=='__main__':unittest.main()
