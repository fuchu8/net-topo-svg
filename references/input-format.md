# JSON 输入与修改方法

先复制 `examples/` 中最接近的 JSON，只修改事实数据。输入不包含绘图源码。图标、自动布局、名称避让和接口标注由脚本负责。

## 通用字段

```json
{
  "style": "2.5d",
  "layout": {"type": "backbone", "main": ["R1", "PC1"]},
  "devices": [
    {"id": "R1", "kind": "router"},
    {"id": "PC1", "kind": "pc", "ip": "192.168.1.10/24", "gateway": "192.168.1.1"}
  ],
  "links": [
    {"from": "R1", "to": "PC1", "from_interface": "GE0/0/0", "to_interface": "E0/0/1", "from_ip": "192.168.1.1/24"}
  ]
}
```

- 设备 `id` 唯一，也是显示名称；可使用中英文、数字、下划线、点、冒号和连字符。
- 顶层 `style` 选整图风格：`2.5d`（默认）或 `rounded`（Ops 同批三方案中的 A，渐变圆角色块）。支持 `2.5D`、`圆角` 等别名，建议案例数据使用标准值。命令行 `--style` 优先于 JSON；不支持在一张图里逐设备混搭。
- `kind` 使用图标 id，见 `topology.py --list-icons`。兼容别名 `R/S/SW3/PC/SERVER/AP/AC/FW`。
- 设备可带 `ip`、`gateway`、`info`（文本数组）。单接口终端 IP 放这里；多接口路由器 IP 通常放链路对应端。
- `from/to` 引用设备 id。物理链路两端必须有接口编号，同一物理接口不能重复连接。
- `from_ip/to_ip` 是本端接口的 IP；可只提供有地址的一端。普通 LSW 二层物理口无 IP，不补造。
- `note` 是链路补充信息，如 `VLAN 10`。不会影响接口编号位置。
- 无线设置 `"medium":"wireless"`，接收端 `to_interface` 可填 `无线网卡`；可选 `caption` 写已知 SSID 等。无线上行不画物理绿点。
- 示例地址只能在用户授权设计示例/实验时使用。改现有实验时按原资料填写，不能直接继承案例 IP。

## 四种自动布局

**backbone**：`layout.main` 指定主干从左到右顺序；`layout.bottom` 如 `{"LSW1":["PC1"]}` 指定下挂设备。`spacing` 默认 310，`bottom_spacing` 默认 240。调整数量时同步修改设备和链路；没有声明的连接不会自动补画。

**hierarchical**：`layout.root` 指根设备，`layout.children` 描述真实父子关系，例如 `{"R1":["LSW1","LSW2"],"LSW1":["PC1","PC2"],"LSW2":["PC3","PC4"]}`。所有设备应属于一棵树，链路与父子关系一致；环网、网状拓扑使用 manual。`leaf_spacing` 默认 320；`level_angles` 默认为 `[30,45]` 度。脚本按叶节点和子树分配水平空间，联动层间距；最小层间距 160，可限制过密时的实际角度。

**aggregation**：恰好两台设备，所有 `links` 都为二者间的有线成员。`layout.bundle` 为已有聚合名称。增减 `links` 即改变成员数量，不要把多个端口合并成一条线。设备会随成员数增加适当放大，以保留接口标注空间。

**access**：`layout.center` 指中心设备；`layout.sides.left/right/bottom` 分别列出外围设备 id。每台外围设备须有一条独立连接中心的链路。左右两组沿相同的外侧角度均匀展开；`fan_angle` 默认 30 度，可在 10–55 度内调整。左右、下方数量可变，IP 在设备对象中改。脚本为密集接口保留设备尺寸与行距。适合一台交换机多终端，非星形图用其他布局。

## 画布与留白

所有布局默认 `"fit":"content"`：全部标注完成后，按完整可见范围对称取景；`padding` 默认 64，至少 32。输出 viewBox 的原点可能不是零，读取或后处理时应保留它，不能擅自改回 `0 0`。

固定尺寸导出可以显式用 `"fit":"canvas"`，保留初始画布，此时不自动裁切和居中。常规拓扑保留 content 模式。增加 IP 可能扩展最终画布，但不会改变设备、绿点与接口编号之间的相对位置。

## 自定义布局

`layout.type` 为 `manual`，提供数值 `width/height`；每台设备提供 `x/y` 和可选 `size`。`x/y` 为设备的连线带中心，不是 SVG 左上角。

`layout.name_groups` 显式按同排或同层级分组，例如 `[["R1","R2"],["PC1","PC2"]]`。分组必须覆盖全部设备且无重复；整组优先下置，遇到线或接口冲突整组换方位。

链路默认沿设备间方向穿过轮廓，直接连线，斜线接点和间隙随方向计算。确有指定端口排布需求时，可用 `from_side/to_side` 和 `from_offset/to_offset` 显式覆盖自动接点。确需转弯时用 `via` 指定少量中间点，例如 `[[400,180],[400,390]]`；首尾线段仍按其方向计算设备接点。不要用折点绕开本应换方位的设备名。

可选 `layout.regions`：每项包含 `x/y/width/height` 以及语义 `label`，用于 VLAN、公司或 OSPF Area 等。区域必须与真实接口归属相符。

## 运行与检查

```bash
python3 scripts/topology.py input.json --strict -o result.svg
python3 scripts/check_topology.py result.svg
python3 scripts/topology.py input.json --style rounded --strict -o rounded.svg
```

不传 `-o` 时 SVG 写 stdout；输入 `-` 时从 stdin 读取 JSON。同一输入可以分别通过 `--style 2.5d`、`--style rounded` 导出两份。`--strict` 在检查警告出现时也停止输出。不要通过删掉 `--strict` 来掩盖实际碰撞；先改数据、留白或坐标，再预览确认。

PNG 预览：先向宿主查询 Node、sharp 路径，再执行：

```bash
python3 scripts/render_preview.py --node /path/to/node --sharp /path/to/sharp -o result.png < result.svg
```

如果宿主已有可用 Node/sharp，可省略对应参数。不要把本机绝对路径写进案例或技能代码。SVG 可以在浏览器直接打开，PNG 依赖缺失不妨碍 SVG 绘图。
