# 双风格图标资产

- `assets/icons/`：32 类 2.5D 图标，对应 `assets/geometry.json`。
- `assets/styles/rounded/icons/`：32 类精修圆角图标，对应同级 `geometry.json`。圆角源于 Ops 与 2.5D 同批设计的 A 方案，不是更早的简易图标库。

每套均有 `sprite.svg`，同样使用 `viewBox="0 0 64 64"`。整张图选择一套，不混用。两套共享下面的设备 id。

| 家族 | 图标 id |
| --- | --- |
| 路由 | `router`、`wireless-router` |
| 交换 | `switch-l2`、`switch-l3`、`switch-stack`、`core-switch` |
| 无线 | `ap`（吸顶）、`ac` |
| 控制 | `controller`、`load-balancer` |
| 安全 | `firewall`、`firehunter`、`anti-ddos`、`ids-ips`、`vpn-gateway` |
| 服务器与存储 | `server`、`server-group`、`log-server`、`nas`、`rack` |
| 光接入 | `olt`、`ont`、`media-converter` |
| 终端 | `pc`、`laptop`、`smartphone`、`phone`、`printer`、`camera` |
| 场景 | `cloud`、`building`、`user` |

配色和形态沿用所选风格的已确认资产。图标内不嵌入设备名称或实验地址；绘图脚本负责标签。仅内联用到的图元，整图自包含。圆角图标使用内联渐变，绘图脚本给每台设备的渐变 ID 加独立命名空间，重复九台 PC 也不会产生 ID 冲突。

每套的几何数据保存可见包络、端口连线带、本体轮廓 `hull` 与可见轮廓 `visible_hull`，用于斜线接点、间隙、文字避让和取景。修改轮廓须同步同套几何数据并重跑双风格案例，不能跨风格复用旧锚点。

这些是自绘的通用网络设备图符，不使用厂商品牌标志。2.5D 扩展保持明暗体积与克制投影；圆角扩展保持同规格底块与白色图符。均须检查 32px 与常用尺寸。只允许引用同一 SVG 已定义 ID 的 `url(#id)`；不允许脚本、外部字体、位图或远程引用。
