import asyncio
import json
import os
import re
import sys
from lucky_data import get_lucky_services
from scanner_frp import get_frp_configs, parse_frp_config
from utils import resolve_domain, get_favicon_url, get_mapping_type

async def main():
    # 加载终端节点别名
    terminal_names = {}
    if os.path.exists('terminal_names.json'):
        try:
            with open('terminal_names.json', 'r', encoding='utf-8') as f:
                terminal_names = json.load(f)
        except Exception as e:
            print(f"[!] 读取 terminal_names.json 失败: {e}")

    if not os.path.exists('config.json'):
        print("[!] 找不到 config.json 文件，请确保该文件存在。")
        return
        
    try:
        with open('config.json', 'r', encoding='utf-8') as f:
            config = json.load(f)
    except Exception as e:
        print(f"[!] 读取 config.json 失败: {e}")
        return

    print("=== 开始生成导航页面 ===")
    output_dir = 'myserv'
    os.makedirs(output_dir, exist_ok=True)
    favicons_dir = os.path.join(output_dir, 'favicons')
    os.makedirs(favicons_dir, exist_ok=True)
    
    # 1. 扫描 FRP 配置
    systemd_dir = config.get("systemd_dir", "/lib/systemd/system")
    print(f"[*] 正在扫描 FRP 服务 (目录: {systemd_dir})...")
    frp_services = get_frp_configs(systemd_dir)
    all_frp_mappings = []
    for s in frp_services:
        mappings = parse_frp_config(s['config_path'])
        all_frp_mappings.extend(mappings)
    print(f"[+] 找到 {len(all_frp_mappings)} 个 FRP 映射")

    # 2. 获取 Lucky 服务 (支持多个服务器)
    lucky_servers = config.get("lucky_servers", [])
    static_mappings = config.get("static_mappings", [])
    lucky_services = []
    
    cache_file = 'lucky_cache.json'
    use_cache = "skiplucky" in sys.argv

    if use_cache and os.path.exists(cache_file):
        print(f"[*] 检测到 skiplucky 参数，正在从缓存 {cache_file} 读取 Lucky 数据...")
        try:
            with open(cache_file, 'r', encoding='utf-8') as f:
                lucky_services = json.load(f)
            print(f"[+] 从缓存加载了 {len(lucky_services)} 个服务")
        except Exception as e:
            print(f"[!] 读取缓存失败: {e}，将重新获取")
            use_cache = False

    if not use_cache or not lucky_services:
        for ls_config in lucky_servers:
            server_name = ls_config.get("name", "未命名Lucky")
            print(f"[*] 正在从 Lucky ({server_name} - {ls_config['url']}) 获取服务信息...")
            try:
                services = await get_lucky_services(ls_config['url'], ls_config['user'], ls_config['pass'], server_name)
                # 给每个service打上服务器标记
                for s in services:
                    s['server_name'] = server_name
                lucky_services.extend(services)
            except Exception as e:
                print(f"[!] 从 {server_name} 获取数据失败: {e}")
        
        # 保存到缓存
        try:
            with open(cache_file, 'w', encoding='utf-8') as f:
                json.dump(lucky_services, f, ensure_ascii=False, indent=2)
            print(f"[+] Lucky 数据已缓存至 {cache_file}")
        except Exception as e:
            print(f"[!] 保存缓存失败: {e}")
    
    print(f"[+] 总计找到 {len(lucky_services)} 个 Lucky 服务")
    
    # DEBUG: 打印原始 Lucky 数据
    print("\n=== DEBUG: 原始 Lucky 服务列表 ===")
    for s in lucky_services:
        print(f"  - Domain: {s['domain']} | Backend: {s['internal_addr']} | Server: {s['server_name']}")
    print("==================================\n")

    # 0. 准备工作：预解析 Lucky 服务器 IP 和 CF DNS 记录
    cf_token = config.get("cloudflare", {}).get("api_token")
    from cf_dns import fetch_all_cf_records, resolve_domain_with_cache, get_lucky_server_ip, is_local_address
    
    # 一次性同步所有 CF 记录
    fetch_all_cf_records(cf_token)
    
    lucky_server_ips = {}
    for ls_config in lucky_servers:
        name = ls_config['name']
        my_ip = ls_config.get('myip')
        resolved_ip = get_lucky_server_ip(ls_config['url'])
        
        # 记录服务器 IP：如果有指定的 myip 则优先使用，否则用解析到的
        lucky_server_ips[name] = my_ip if my_ip else (resolved_ip if resolved_ip else "未知")

    # 3. 整合数据
    print(f"[*] 正在整合数据并处理路径分析 (共 {len(lucky_services)} 个条目)...")
    final_data = []

    for i, ls in enumerate(lucky_services):
        raw_domain = ls['domain']
        internal_addr = ls['internal_addr']
        server_name = ls['server_name']
        lucky_ip = lucky_server_ips.get(server_name)
        
        # A. 解析域名真实 IP
        domain = raw_domain.split(':')[0]
        frontend_port = raw_domain.split(':')[1] if ':' in raw_domain else None

        if (i+1) % 10 == 0 or i == 0:
            print(f"[*] 正在处理第 {i+1}/{len(lucky_services)} 个服务: {raw_domain}")
        
        # 优先用 CF 缓存查询，拿不到再用系统 DNS
        cf_rec = resolve_domain_with_cache(domain)
        if cf_rec:
            ip = cf_rec['content']
            if cf_rec.get('proxied'):
                mapping_provider = "CF proxy"
            else:
                mapping_provider = config.get("ip_aliases", {}).get(ip, "Direct")
        else:
            ip = resolve_domain(domain)
            mapping_provider = config.get("ip_aliases", {}).get(ip, get_mapping_type(ip))
        
        
        # B. 检查静态映射
        matched_sm = None
        for sm in static_mappings:
            if re.match(sm['pattern'], domain):
                matched_sm = sm
                break
        

        # C. 确定访问端口
        display_port = frontend_port
        if matched_sm:
            p_map = matched_sm.get("port_map", {})
            local_p = internal_addr.split(':')[-1] if ':' in internal_addr else ""
            if str(frontend_port) in p_map:
                display_port = p_map[str(frontend_port)]
            elif str(local_p) in p_map:
                display_port = p_map[str(local_p)]

        # D. 深度路径溯源 (FRP 关联)
        
        # D.1 前置 FRP (Entry ➔ FRPS ➔ Lucky)
        matching_pre_frp = None
        path_pre_frp_info = ""
        target_fp = str(frontend_port) if frontend_port else ("443" if ls.get("protocol") == "https" else "80")


        # 重点：如果服务没有匹配 static_mappings，且 Lucky 本身在内网，探测 Pre-Lucky FRP
        if not matched_sm:
            for fm in all_frp_mappings:
                f_server = fm.get('server_addr', '').lower()
                p_remote = str(fm.get('remote_port'))
                l_ip = fm.get('local_ip', '').lower()
                l_port = str(fm.get('local_port'))
                
                # 智能 IP 匹配：如果 server_addr 是域名，尝试解析
                f_server_ip = f_server
                if not re.match(r'^\d+\.\d+\.\d+\.\d+$', f_server):
                    from cf_dns import resolve_domain_with_cache
                    cf_rec_s = resolve_domain_with_cache(f_server)
                    if cf_rec_s: f_server_ip = cf_rec_s['content']
                    else:
                        from utils import resolve_domain as rd
                        f_server_ip = rd(f_server)

                # 匹配逻辑：
                # 1. FRP 服务的 server_addr 匹配我们解析到的域名的 IP (即 FRPS)
                # 2. FRP 的 remote_port OR local_port 匹配前端访问端口
                # 3. FRP 的 local_ip 指向当前 Lucky 的 IP (或回环地址)
                ip_match = (f_server_ip.lower() == ip.lower())
                port_match = (p_remote == target_fp or l_port == target_fp)
                local_match = (l_ip in ['127.0.0.1', 'localhost', '0.0.0.0', (lucky_ip or "").lower()])
                

                if ip_match and port_match and local_match:
                    matching_pre_frp = fm
                    r_name = fm.get('name', '未命名')
                    source = fm.get('source_file', '未知')
                    
                    # 构造更准确的描述
                    if l_port == target_fp and p_remote != target_fp:
                        path_pre_frp_info = f"FRP 入站 | {source}({r_name}): {p_remote} ➔ {l_port} (内网Lucky)"
                    else:
                        path_pre_frp_info = f"FRP 入站 | {source}({r_name}): {p_remote} ➔ {l_port}"
                    
                    # 关键修复：既然是通过 FRP 入站，对外访问端口必须是 remote_port
                    display_port = p_remote
                        
                    print(f"  [*] 匹配 Pre-Lucky FRP: {path_pre_frp_info} (更新对外端口为: {display_port})")
                    break
            

        # D.2 后置 FRP (Lucky ➔ 后端服务)
        matching_frp = None
        path_frp_info = ""
        
        # 提取 Lucky 后端端口
        lucky_backend_port = None
        if ':' in internal_addr:
            try:
                # 兼容 http://127.0.0.1:8099/ 或 127.0.0.1:8099
                addr_clean = internal_addr.split('://')[-1].split('/')[0]
                if ':' in addr_clean:
                    lucky_backend_port = addr_clean.split(':')[-1]
            except: pass

        if lucky_backend_port:
            # 提取原始协议
            original_proto = ""
            if "://" in internal_addr:
                original_proto = internal_addr.split("://")[0] + "://"

            # print(f"[DEBUG] 正在为 {domain} 寻找 FRP 关联... 后端端口: {lucky_backend_port}, Lucky服务器IP: {lucky_ip}")
            # 寻找关联的 FRP 规则
            for fm in all_frp_mappings:
                # 核心逻辑：Lucky 后端访问的端口，在 FRP 体系中通常是 remote_port (由客户端穿透到服务端)
                
                # 首先根据端口匹配
                p_remote = str(fm.get('remote_port'))
                p_local = str(fm.get('local_port'))
                
                port_match = (p_remote == str(lucky_backend_port) or p_local == str(lucky_backend_port))
                
                if port_match:
                    print(f"  [?] 端口匹配! 规则详情: {fm}")
                    
                    # 其次验证这是否是属于当前 Lucky 所在服务器的 FRP 链路
                    f_server = fm.get('server_addr', '').lower()
                    l_ip_target = (lucky_ip or "").lower()
                    
                    server_match = False
                    # 1. 如果 FRP 连接的地址就是 Lucky 的公网 IP
                    if l_ip_target and f_server == l_ip_target:
                        server_match = True
                    # 2. 如果 Lucky 本身就在本机运行
                    elif f_server in ['127.0.0.1', 'localhost', '0.0.0.0']:
                        server_match = True
                    # 3. 兜底：如果 Lucky IP 是私有地址或未解析，且 FRP 目标看起来是内网，尝试匹配
                    
                    if server_match:
                        matching_frp = fm
                        l_ip = fm.get('local_ip', '127.0.0.1')
                        l_port = fm.get('local_port', '未知')
                        r_port = fm.get('remote_port', '未知')
                        source = fm.get('source_file', '未知配置')
                        rule_name = fm.get('name', '匿名规则')
                        
                        # 把规则名也放进显示信息中
                        display_source = f"{source}({rule_name})"
                        
                        # 拼接带协议的详细路径
                        frp_target_with_proto = f"{original_proto}{l_ip}:{l_port}"
                        
                        if str(r_port) == str(lucky_backend_port):
                            path_frp_info = f"FRP 穿透 | {display_source}: ➔ {frp_target_with_proto}"
                        else:
                            path_frp_info = f"FRP 关联 | {display_source}: ➔ {frp_target_with_proto}"
                        
                        print(f"[*] {domain} ➔ 成功匹配 FRP 路径: {display_source} ➔ {frp_target_with_proto}")
                        break
                    else:
                        pass
                        # print(f"  [x] IP 不匹配: FRP指向 {f_server} != Lucky所在的 {l_ip_target}")

        # E. 构造 URL
        # 优先遵守 Lucky 前端抓取到的原始协议
        protocol = ls.get("protocol", "http")
        
        # 只有在静态映射中显式开启 TLS 时才强制 https，不再根据端口自动判断
        if matched_sm and matched_sm.get("TLS") is True:
            protocol = "https"

        if protocol == "https":
            if display_port and str(display_port) != "443":
                access_url = f"https://{domain}:{display_port}"
            else:
                access_url = f"https://{domain}"
        else:
            if display_port and str(display_port) != "80":
                access_url = f"http://{domain}:{display_port}"
            else:
                access_url = f"http://{domain}"
        
        # F. 处理 STUN 路由分析 (如果配置了 stun_route)
        stun_server_name = "未知"
        stun_internal_addr = "未知"
        stun_node_ip = None
        if matched_sm and "stun_route" in matched_sm:
            for pattern, replacement in matched_sm["stun_route"].items():
                if re.search(pattern, domain):
                    # 根据规则生成目标 STUN 域名，并清理掉由于正则转义可能带入的斜杠
                    target_stun_domain = re.sub(pattern, replacement, domain).replace('\\', '')
                    # 在已抓取的 Lucky 服务中寻找对应条目
                    for other_ls in lucky_services:
                        # 重点：Lucky 原始 domain 可能包含端口，需要统一只比较 host
                        other_host = other_ls['domain'].split(':')[0]
                        if other_host == target_stun_domain:
                            # 修改要求：stun_server_name 加 () 内添加转换后的服务地址
                            stun_server_name = f"{other_ls.get('server_name', '未知')} ({target_stun_domain})"
                            stun_internal_addr = other_ls.get('internal_addr', '未知')
                            # 捕获 STUN 节点的真实 IP
                            stun_node_ip = lucky_server_ips.get(other_ls.get('server_name', ''))
                            break
                    break

        # G. 确定最终端点地址 (Internal Address)
        # 优先级：STUN 后端 > FRP 本地地址 > Lucky 后端
        raw_end_addr = "未知"
        node_ip = lucky_ip # 默认使用当前节点的服务器 IP (已包含 myip 优先逻辑)
        
        if stun_internal_addr != "未知":
            raw_end_addr = stun_internal_addr
            if stun_node_ip: 
                node_ip = stun_node_ip
        elif matching_frp:
            # 同样保留协议
            original_proto = ""
            if "://" in internal_addr:
                original_proto = internal_addr.split("://")[0] + "://"
            raw_end_addr = f"{original_proto}{matching_frp.get('local_ip', '127.0.0.1')}:{matching_frp.get('local_port', '未知')}"
        else:
            raw_end_addr = internal_addr

        # 处理 127.0.0.1 替换逻辑
        final_internal_addr = raw_end_addr
        if "127.0.0.1" in raw_end_addr or "localhost" in raw_end_addr:
            if node_ip and node_ip != "未知":
                final_internal_addr = raw_end_addr.replace("127.0.0.1", node_ip).replace("localhost", node_ip)

        # H. 描述链条构建
        path_segments = []
        path_segments.append(f"{ip} ({mapping_provider})")
        if path_pre_frp_info:
            path_segments.append(path_pre_frp_info)
        path_segments.append(f"{server_name} ({lucky_ip})")
        path_segments.append(f"后端: {internal_addr}")
        if matching_frp:
            path_segments.append(path_frp_info)

        if matched_sm:
            chain = matched_sm['description'].replace("{server_name}", server_name).replace("{internal_addr}", internal_addr).replace("{ip}", ip)
            chain = chain.replace("{port}", str(display_port) if display_port else "")
            # 注入 STUN 变量 (如果有)
            chain = chain.replace("{stun_server_name}", stun_server_name).replace("{stun_internal_addr}", stun_internal_addr)
            
            # 如果有 FRP 穿透信息，尝试追加到描述中（如果用户没写定义）
            if matching_frp and "FRP" not in chain:
                chain += f" ➔ {path_frp_info}"
        else:
            chain = " ➔ ".join(path_segments)

        final_data.append({
            "domain": domain,
            "server_name": server_name,
            "icon": f"favicons/{domain}.png",
            "internal_addr": final_internal_addr,
            "chain": chain,
            "frp_info": path_frp_info if path_frp_info else "无",
            "ip": ip,
            "access_url": access_url,
            "comment": matched_sm.get("comment", "") if matched_sm else "",
            "undisplay": matched_sm.get("undisplay", False) if matched_sm else False
        })

    # 4. 下载并缓存 Favicon
    if "skipicon" in sys.argv:
        print("\n[*] 检测到 skipicon 参数，跳过图标获取步骤。")
        # 确保每个条目的 icon 路径仍然指向现有的本地文件（如果存在）
        for s in final_data:
            domain = s['domain']
            real_path = os.path.join(favicons_dir, f"{domain}.png")
            pillow_path = os.path.join(favicons_dir, f"{domain}.pillow.png")
            if os.path.exists(real_path):
                s['icon'] = f"favicons/{domain}.png"
            elif os.path.exists(pillow_path):
                s['icon'] = f"favicons/{domain}.pillow.png"
            else:
                s['icon'] = "favicons/default.png"
    else:
        import requests
        import urllib3
        from urllib.parse import urljoin, urlparse
        # 禁用 HTTPS 证书验证警告
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        
        print("\n[*] 正在处理图标下载与缓存...")
    
        for s in final_data:
            domain = s['domain']
            access_url = s['access_url']
            
            real_icon_path = os.path.join(favicons_dir, f"{domain}.png")
            pillow_icon_path = os.path.join(favicons_dir, f"{domain}.pillow.png")
            
            # 初始检查：如果已经有真实图标，直接使用
            if os.path.exists(real_icon_path):
                s['icon'] = f"favicons/{domain}.png"
                print(f"  [#] 真实图标已存在: {domain}")
                continue
                
            # 如果只有 Pillow 图标或者什么都没有，则进入下载逻辑
            is_retry = os.path.exists(pillow_icon_path)
            print(f"  [>] {'尝试更新占位图标' if is_retry else '准备下载新图标'} | 域: {domain}")
            
            success = False
            
            # 1. 尝试从服务的直接地址获取 /favicon.ico
            try:
                parsed = urlparse(access_url)
                base_url = f"{parsed.scheme}://{parsed.netloc}"
                target_favicon = urljoin(base_url, '/favicon.ico')
                print(f"    - 正在尝试直连探测: {target_favicon}")
                
                r = requests.get(target_favicon, timeout=3, verify=False)
                if r.status_code == 200 and len(r.content) > 100:
                    with open(real_icon_path, 'wb') as f:
                        f.write(r.content)
                    print(f"    [+] 直连下载成功! ✅")
                    success = True
                else:
                    print(f"    [!] 直连不可用 (HTTP {r.status_code})")
            except requests.exceptions.SSLError:
                print(f"    [!] 直连失败: SSL 证书错误")
            except requests.exceptions.ConnectionError:
                print(f"    [!] 直连失败: 无法建立连接")
            except requests.exceptions.Timeout:
                print(f"    [!] 直连失败: 请求超时")
            except Exception as e:
                print(f"    [!] 直连请求异常: {str(e)[:50]}...")
            
            # 2. 如果直连探测失败，尝试解析网页 HTML 源码寻找图标路径
            if not success:
                try:
                    print(f"    - 正在分析首页 HTML 源码: {access_url}")
                    r_html = requests.get(access_url, timeout=5, verify=False)
                    if r_html.status_code == 200:
                        pattern = r'<link[^>]+rel=["\'](?:shortcut )?icon["\'][^>]+href=["\']([^"\']+)["\']'
                        match = re.search(pattern, r_html.text, re.IGNORECASE)
                        if not match:
                            pattern_alt = r'<link[^>]+href=["\']([^"\']+)["\'][^>]+rel=["\'](?:shortcut )?icon["\']'
                            match = re.search(pattern_alt, r_html.text, re.IGNORECASE)
                        
                        if match:
                            icon_href = match.group(1)
                            target_favicon = urljoin(access_url, icon_href)
                            print(f"    - 发现网页内嵌图标路径: {target_favicon}")
                            r_icon = requests.get(target_favicon, timeout=3, verify=False)
                            if r_icon.status_code == 200 and len(r_icon.content) > 100:
                                with open(real_icon_path, 'wb') as f:
                                    f.write(r_icon.content)
                                print(f"    [+] 从网页源码解析下载成功 ✅")
                                success = True
                    else:
                        print(f"    [!] 首页加载失败 (HTTP {r_html.status_code})")
                except Exception as e:
                    print(f"    [!] 源码分析异常: {str(e)[:50]}")

            # 3. 如果还是失败，使用 Google Favicon 服务
            if not success:
                try:
                    google_url = f"https://www.google.com/s2/favicons?domain={domain}&sz=64"
                    print(f"    - 正在尝试 Google 备选接口: {google_url}")
                    r = requests.get(google_url, timeout=5)
                    if r.status_code == 200 and len(r.content) > 500:
                        with open(real_icon_path, 'wb') as f:
                            f.write(r.content)
                        print(f"    [+] Google 接口下载成功 ✅")
                        success = True
                except Exception as e:
                    print(f"    [!] Google 接口失败: {str(e)[:50]}")

            # 4. 设置最终使用的图标路径，并决定是否要清理 Pillow 图标
            if success:
                s['icon'] = f"favicons/{domain}.png"
                if os.path.exists(pillow_icon_path):
                    try: os.remove(pillow_icon_path)
                    except: pass
            else:
                # 所有下载均失败，只能用 Pillow 兜底
                if not os.path.exists(pillow_icon_path):
                    try:
                        from PIL import Image, ImageDraw, ImageFont
                        import random
                        first_char = domain[0].upper() if domain else "S"
                        size = (64, 64)
                        bg_color = (random.randint(40, 200), random.randint(40, 200), random.randint(40, 200))
                        img = Image.new('RGB', size, color=bg_color)
                        draw = ImageDraw.Draw(img)
                        
                        font = None
                        for f_name in ["msyh.ttc", "arial.ttf", "simhei.ttf", "DejaVuSans.ttf"]:
                            try:
                                font = ImageFont.truetype(f_name, 40)
                                break
                            except: continue
                        if not font: font = ImageFont.load_default()
                        
                        try: left, top, right, bottom = draw.textbbox((0, 0), first_char, font=font)
                        except: right, bottom = draw.textsize(first_char, font=font); left, top = 0, 0
                        
                        pos = ((size[0] - (right-left)) / 2, (size[1] - (bottom-top)) / 2 - 4)
                        draw.text(pos, first_char, fill="white", font=font)
                        img.save(pillow_icon_path)
                        print(f"    [+] 已生成新的本地占位图标 ✅")
                    except Exception as e:
                        print(f"    [!] 本地图标生成彻底失败: {e}")
                
                s['icon'] = f"favicons/{domain}.pillow.png" if os.path.exists(pillow_icon_path) else "favicons/default.png"

    # 5. 保存数据
    # 同时保存 JSON 供调试，并生成内嵌数据的 HTML 提高便携性
    output_payload = {
        "ip_aliases": config.get("ip_aliases", {}),
        "services": final_data,
        "frp_mappings": all_frp_mappings,
        "terminal_names": terminal_names
    }
    
    services_path = os.path.join(output_dir, 'services.json')
    with open(services_path, 'w', encoding='utf-8') as f:
        json.dump(output_payload, f, ensure_ascii=False, indent=2)
    print(f"[+] 数据已保存至 {services_path}")

    # 5. 生成 HTML
    if os.path.exists('template.html'):
        with open('template.html', 'r', encoding='utf-8') as f:
            tmpl = f.read()
        
        # 将数据填充到模板中
        html_content = tmpl.replace('var services = [];', f'var services = {json.dumps(output_payload["services"], ensure_ascii=False)};')
        # 增加 ip_aliases 填充
        html_content = html_content.replace('var ipAliases = {};', f'var ipAliases = {json.dumps(output_payload["ip_aliases"], ensure_ascii=False)};')
        # 增加 frp_mappings 填充
        html_content = html_content.replace('var frp_mappings = [];', f'var frp_mappings = {json.dumps(output_payload["frp_mappings"], ensure_ascii=False)};')
        # 增加 terminal_names 填充
        html_content = html_content.replace('var terminalNames = {};', f'var terminalNames = {json.dumps(output_payload["terminal_names"], ensure_ascii=False)};')

        index_path = os.path.join(output_dir, 'index.html')
        with open(index_path, 'w', encoding='utf-8') as f:
            f.write(html_content)
        print(f"[+] 导航页面 (数据内嵌版) 已生成: {index_path}")

if __name__ == "__main__":
    asyncio.run(main())
