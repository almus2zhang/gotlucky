# GotLucky - 内网服务自动化导航系统

本项目通过自动抓取 Lucky 服务器、扫描 FRP 穿透配置以及结合 Cloudflare DNS 信息，自动生成一个美观、交互式的内网服务导航页面。支持网格视图和拓扑连接视图，并具备实时全文搜索功能。

## 配置文件设定 (`config.json`)

配置文件位于项目根目录，名为 `config.json`。以下是各配置项的详细说明：

### 1. 节点别名 (`ip_aliases`)
用于将冰冷的 IP 地址替换为直观的设备名称，用于拓扑视图根节点显示名。
```json
"ip_aliases": {
    "10.0.0.10": "Home-NAS",
    "1.2.3.4": "Cloud-Node-A",
    "10.0.0.1": "Main-Router"
}
```

### 2. Lucky 服务器配置 (`lucky_servers`)
程序会通过 Playwright 自动登录这些服务器并抓取所有的 Web 服务规则。
- `name`: 服务器展示名称。
- `url`: Lucky 管理界面的访问地址。
- `user`: 登录用户名。
- `pass`: 登录密码。
- `myip` (可选): 该服务器的公网出口 IP，用于路径溯源逻辑。

```json
"lucky_servers": [
    {
        "name": "Home-Lucky",
        "url": "https://lucky.example.com",
        "user": "admin",
        "pass": "password",
        "myip": "8.8.8.8"
    }
]
```

### 3. Cloudflare 配置 (`cloudflare`)
用于获取 DNS 记录和解析状态（是否开启了代理）。
- `api_token`: 具有 DNS 读取权限的 Cloudflare API 令牌。

```json
"cloudflare": {
    "api_token": "YOUR_CLOUDFLARE_API_TOKEN"
}
```

### 4. 静态映射与高级逻辑 (`static_mappings`)
这是系统的核心，用于定义特定域名的展示、转换和分析逻辑。

#### A. 端口映射 (`port_map`)
用于解决 Lucky 前端端口与实际访问端口不一致的情况（例如经过了外部防火墙或路由器转发）。
- **逻辑**：如果该域名的“前端端口”或 Lucky 识别到的“后端端口”命中了 `port_map` 的 Key，建议的访问 URL 就会使用对应的 Value 作为端口。
- **例子**：Lucky 规则里写的是 `8099` 端口，但在公网上是通过 `18099` 访问的。
```json
{
    "pattern": "nas.example.com",
    "port_map": { "8099": "18099" }
}
```

#### B. STUN 路由跳转 (`stun_route`)
用于处理 Lucky 复杂的“穿透 + 跳转”场景。例如：A 服务器做 STUN 穿透，但实际上最终数据流向了 B 服务器。
- **逻辑**：`pattern` 是域名匹配正则，`replacement` 是要跳转到的“逻辑目标域名”。程序会在所有已抓取的 Lucky 规则中寻找这个“目标域名”，并提取该域名的真实物理 IP 作为当前服务的最终端点。
- **例子**：当访问 `service.example.com` 时，它的流量实际上是经过 `relay.example.com` 节点转发的。
```json
"stun_route": {
    "service.example.com": "relay.example.com"
}
```

### 5. 高级溯源技术详解

#### I. FRP 自动化溯源流程
系统会自动扫描 `/lib/systemd/system` 下的 `frpc` 相关服务文件，并尝试将 Lucky 的“后端地址”与 FRP 建立关联。

**溯源步骤示例：**
1. **Lucky 端**：在服务器 `Cloud-Node-A` 上抓到一个规则：`myblog.example.com ➔ 127.0.0.1:6001`。
2. **分析**：程序识别到该服务的后端出口是本地 `6001` 端口。
3. **FRP 扫描**：程序在所有 FRP 配置文件中寻找 `remote_port = 6001` 且服务器指向 `Cloud-Node-A-IP` 的规则。
4. **发现关联**：找到一个 FRP 规则，其本地指向 `10.0.0.20:80`（内部 Web 服务器）。
5. **最终结果**：拓扑图会实时绘制一条链路：`访客 ➔ Cloud-Node-A ➔ [FRP穿透] ➔ 10.0.0.20:80`。

#### II. 127.0.0.1 智能替换逻辑
为了在拓扑图中显示真实的物理路径，系统会自动处理“本地回环”地址。
- **场景**：Lucky 显示后端地址为 `http://127.0.0.1:5000`。
- **处理**：系统识别出这一规则运行在 `Media-Server` 服务器上（IP 为 `10.0.0.100`），会自动将 `127.0.0.1` 替换为 `10.0.0.100`。
- **效果**：终端节点会显示为 `http://10.0.0.100:5000`，使您可以一眼看出服务运行在哪台物理设备上。

## 运行环境与执行

1. **环境准备**:
   ```bash
   pip install -r requirements.txt
   playwright install chromium
   ```

2. **生成页面**:
   ```bash
   python main.py
   ```
   - 使用 `python main.py skipicon` 可跳过 Favicon 下载，加快生成速度。

3. **查看结果**:
   打开生成的 `index.html` 即可看到完整的导航面板。
