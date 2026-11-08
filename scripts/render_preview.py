#!/usr/bin/env python3
"""Render SVG stdin to PNG stdout with optional host-provided Node/sharp paths."""
import argparse
from pathlib import Path
import shutil
import subprocess
import sys
from check_topology import validate_svg


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--node',help='Node 可执行文件；默认从 PATH 查找')
    p.add_argument('--sharp',help='sharp 模块目录；默认由 Node 模块解析查找')
    p.add_argument('--width',type=int,help='可选 PNG 宽度')
    p.add_argument('-o','--output',help='可选输出文件；默认写 stdout')
    args=p.parse_args()
    try:
        svg=sys.stdin.buffer.read();validate_svg(svg)
        node=args.node or shutil.which('node')
        if not node:raise ValueError('未找到 Node，请通过 --node 提供宿主路径；SVG 生成只需要 Python 3')
        if args.width is not None and args.width<=0:raise ValueError('PNG 宽度必须为正数')
        js="""const sharp=require(process.argv[1]||'sharp');const b=[];
process.stdin.on('data',c=>b.push(c));process.stdin.on('end',async()=>{
try{let s=sharp(Buffer.concat(b));const w=Number(process.argv[2]);if(w)s=s.resize({width:w});process.stdout.write(await s.png().toBuffer());}
catch(e){process.stderr.write('PNG render failed: '+e.message);process.exitCode=1;}});"""
        result=subprocess.run([node,'-e',js,'--',args.sharp or '',str(args.width or 0)],input=svg,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=60)
        if result.returncode or not result.stdout.startswith(b'\x89PNG\r\n\x1a\n'):raise ValueError(result.stderr.decode(errors='replace') or 'PNG 栅格化失败')
        if args.output:Path(args.output).write_bytes(result.stdout)
        else:sys.stdout.buffer.write(result.stdout)
        return 0
    except (OSError,ValueError,subprocess.TimeoutExpired) as exc:
        print(str(exc),file=sys.stderr);return 2


if __name__=='__main__':sys.exit(main())
