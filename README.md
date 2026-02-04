# GotLucky - 内网服务自动化导航系统

> 🚀 **自动抓取、智能溯源、美观展示** —— 打造属于你的全自动内网服务仪表盘。

[![Live Demo](https://img.shields.io/badge/Live-Demo-brightgreen?style=for-the-badge)](https://almus2zhang.github.io/gotlucky/demo/index.html)

GotLucky 是一个旨在解决“内网服务难以管理和记忆”的自动化系统。它通过自动登录你的 [Lucky](https://github.com/gshang2017/lucky) 服务器抓取 Web 规则，结合 FRP 穿透信息和 Cloudflare DNS 数据，自动绘制出完整的服务访问拓扑和高效的导航列表。

---

## ✨ 核心特性

- 🌐 **全自动同步**：通过 Playwright 模拟登录，一键抓取多个 Lucky 节点的 Web 服务配置。
- 🔍 **智能路径溯源**：
  - **FRP 关联**：自动扫描系统配置，将 Lucky 入口与后端的 FRP 隧道进行精准匹配。
  - **回环 IP 替换**：自动将 `127.0.0.1` 映射为真实的服务器物理物理 IP。
  - **STUN 路由跳转**：支持复杂的跨节点跳转逻辑分析。
- 🎨 **多维度交互视角**：
  - **网格视图 (Grid)**：传统的卡片式导航。
  - **导航视图 (Navigation)**：以终端节点为核心的分组列表，支持**局域网智能探测**（同网络直连，异网络通过网关）。
  - **拓扑视图 (Topology)**：可视化展示“入口 ➔ 终端设备 ➔ 业务服务”的完整链路。
  - **FRP 视图**：专注于穿透映射关系的清晰概览。
- 🚀 **极致性能与智能**：
  - 支持 **实时全文搜索**。
  - 具备 **在线状态检查**（Online Check）功能。
  - 自带 **Demo 模式**，方便演示与分享。

---

## 🛠️ 快速开始

### 1. 安装环境

确保系统中已安装 Python 3.8+。

```bash
# 拉取代码
git clone https://github.com/almus2zhang/gotlucky.git
cd gotlucky

# 安装依赖
pip install -r requirements.txt
playwright install chromium
```

### 2. 配置文件 (`config.json`)

在项目根目录创建或修改 `config.json`。以下是各配置项的详细说明：

#### 🚀 Lucky 服务器配置 (`lucky_servers`)
程序的核心入口。通过 Playwright 抓取这些服务器上的所有 Web 规则。
```json
"lucky_servers": [
    {
        "name": "家里的老牛",          // 服务器展示名称
        "url": "http://192.168.1.1:8800", // Lucky 管理后台地址
        "user": "admin",                // 登录用户名
        "pass": "password",             // 登录密码
        "myip": "1.2.3.4"               // [可选] 该节点的公网出口 IP，用于链路诊断
    }
]
```

#### ☁️ Cloudflare 配置 (`cloudflare`)
用于同步域名的 Proxy 状态（是否开启了小云朵）及 DNS 解析记录。
```json
"cloudflare": {
    "api_token": "YOUR_CF_TOKEN" // 需具备 DNS:Read 权限
}
```

#### 🏷️ 节点别名 (`ip_aliases`)
将冰冷的 IP 地址替换为直观的设备名称，在拓扑视图中作为根节点名称显示。
```json
"ip_aliases": {
    "192.168.1.10": "家庭存储 (NAS)",
    "192.168.1.1": "主路由器",
    "45.67.89.1": "香港中转 VPS"
}
```

#### 🛠️ 静态映射与高级逻辑 (`static_mappings`)
用于定义特定域名的展示转换和复杂的 STUN/FRP 溯源逻辑。
```json
"static_mappings": [
    {
        "pattern": "nas.example.com", 
        "port_map": { 
            "8099": "18099" // Lucky 内部转发 8099，但外部访问端口是 18099
        }
    },
    {
        "pattern": ".*.lab.local",
        "stun_route": "gateway.example.com" // 若匹配此正则，其物理端点强制指向 gateway 的 IP
    }
]
```

### 3. 生成页面

```bash
# 正常模式（会尝试下载 Favicon）
python main.py

# 快速模式（跳过图标下载）
python main.py skipicon

# 演示模式（使用内置的演示数据集生成 demo 目录）
python main.py demo
```

---

## 📖 核心功能详解

### 智能跳转逻辑 (Smart Access)
在“导航视图”中，点击终端卡片时系统会：
1. **WebRTC 检测**：探测当前浏览器所在环境的内网 IP。
2. **子网匹配**：若本机 IP 与目标终端处于同一网段，则直接打开内网地址。
3. **探测连接**：若匹配失败，系统会尝试探测内网连通性。若无法直连，则自动切换为通过 **Lucky 公网入口** 访问。

### 拓扑链路分析
系统会将复杂的内网架构抽象为：
`访客环境 ➔ 入口节点 (Cloudflare/Lucky) ➔ [FRP/Direct] ➔ 物理服务器 (终端节点) ➔ 最终服务`

在**拓扑视图**中，你可以清晰地通过动态连线看到服务的实时运行路径及归属设备。

---

## 📂 目录结构

- `main.py`: 系统核心逻辑，负责抓取、分析与数据生成。
- `template.html`: 基于现代 CSS 和原生 JS 构建的响应式前端模板。
- `cf_dns.py`: Cloudflare DNS 信息同步模块。
- `demo/`: 预生成的动态演示环境及图标库。

---

## 🤝 参与贡献

欢迎提交 Issue 或 Pull Request 来改进路径算法或丰富前端交互。

*如果这个项目对你有帮助，欢迎点个 ⭐️ Star！*
