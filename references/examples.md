# 四个可执行案例

案例保留同一份 JSON 输入，以及两种风格的 SVG/PNG。它们是可运行的版式依据，不能用图片替代数据，也不能把案例地址套进真实实验。

| 案例 | 输入 | 结果 | 检查重点 |
| --- | --- | --- | --- |
| 基础接入拓扑 | [basic-access.json](../examples/basic-access.json) | [SVG](../examples/basic-access.svg) · [PNG](../examples/basic-access.png) | 横向主干、下挂 PC、无线手机、端点关联 IP、整组名称避让 |
| 四链路聚合 | [link-aggregation.json](../examples/link-aggregation.json) | [SVG](../examples/link-aggregation.svg) · [PNG](../examples/link-aggregation.png) | 四条独立成员、八个端点、两端编号、统一设备名位置 |
| 九终端接入 | [multi-access.json](../examples/multi-access.json) | [SVG](../examples/multi-access.svg) · [PNG](../examples/multi-access.png) | 左 3、右 4、下 2，直接斜线，每台 PC 有 IP，同层名称统一 |
| 分层接入拓扑 | [hierarchical-access.json](../examples/hierarchical-access.json) | [SVG](../examples/hierarchical-access.svg) · [PNG](../examples/hierarchical-access.png) | 子树对称、同层角度、轮廓接点、对称取景 |

圆角版由相同输入加 `--style rounded` 生成：

| 案例 | 圆角 SVG | 圆角 PNG |
| --- | --- | --- |
| 基础接入拓扑 | [SVG](../examples/basic-access-rounded.svg) | [PNG](../examples/basic-access-rounded.png) |
| 四链路聚合 | [SVG](../examples/link-aggregation-rounded.svg) | [PNG](../examples/link-aggregation-rounded.png) |
| 九终端接入 | [SVG](../examples/multi-access-rounded.svg) | [PNG](../examples/multi-access-rounded.png) |
| 分层接入拓扑 | [SVG](../examples/hierarchical-access-rounded.svg) | [PNG](../examples/hierarchical-access-rounded.png) |

模型能力较弱时，优先复制案例修改 JSON。相同输入交给同一脚本会得到相同 SVG；改主机名、接口、地址、成员数或终端数量，无须模型自行画几何。

这不等于保证任何模型都能设计复杂新拓扑。陌生层级、特殊区域划分和复杂避让仍需检查真实语义及人工预览。新增分层案例专门覆盖斜线和整体居中的回归；案例按场景命名，不保留多个历史版式。

回归检查：

```bash
python3 -m unittest discover -s tests -v
python3 scripts/check_topology.py --all --quiet
```
