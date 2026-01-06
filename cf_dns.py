import requests
import json
import socket

# 全局缓存
_cf_cache = []

def fetch_all_cf_records(api_token):
    """
    一次性获取所有 Zone 下的所有 A/AAAA 记录并缓存到内存中
    """
    global _cf_cache
    if not api_token:
        return
        
    print("[*] [CF-DNS] 正在同步 Cloudflare 所有 DNS 记录...")
    try:
        headers = {
            "Authorization": f"Bearer {api_token}",
            "Content-Type": "application/json"
        }
        
        # 1. 获取所有 Zones
        zones_resp = requests.get("https://api.cloudflare.com/client/v4/zones", headers=headers, params={"per_page": 50})
        zones = zones_resp.json().get("result", [])
        
        temp_cache = []
        for zone in zones:
            zone_id = zone['id']
            # 2. 获取该 Zone 下的所有记录 (支持分页，这里简单取前 1000 条)
            records_resp = requests.get(
                f"https://api.cloudflare.com/client/v4/zones/{zone_id}/dns_records", 
                headers=headers, 
                params={"per_page": 1000, "type": "A,AAAA"}
            )
            records = records_resp.json().get("result", [])
            for rec in records:
                temp_cache.append({
                    "name": rec['name'].lower(),
                    "content": rec['content'],
                    "proxied": rec['proxied'],
                    "type": rec['type']
                })
        
        _cf_cache = temp_cache
        print(f"[+] [CF-DNS] 同步完成，共加载 {len(_cf_cache)} 条记录")
    except Exception as e:
        print(f"[!] [CF-DNS] 同步失败: {e}")

def resolve_domain_with_cache(domain):
    """
    使用本地缓存的记录进行匹配 (支持精确和泛域名)
    返回完整的 record 字典，如果没找到则返回 None
    """
    global _cf_cache
    if not _cf_cache:
        return None
        
    dom_lower = domain.lower()
    
    # 1. 精确匹配
    for rec in _cf_cache:
        if rec['name'] == dom_lower:
            return rec
            
    # 2. 泛域名匹配
    for rec in _cf_cache:
        if '*' in rec['name']:
            suffix = rec['name'].replace('*', '')
            if dom_lower.endswith(suffix) and dom_lower != suffix.lstrip('.'):
                return rec
                
    return None

def get_lucky_server_ip(lucky_url):
    """从 Lucky URL 中解析出服务器的 IP"""
    try:
        from urllib.parse import urlparse
        parsed = urlparse(lucky_url)
        hostname = parsed.hostname
        return socket.gethostbyname(hostname)
    except:
        return None

def is_local_address(addr):
    """判断一个地址是否是本机/回环地址"""
    local_identifiers = ['127.0.0.1', 'localhost', '0.0.0.0']
    return any(id in addr for id in local_identifiers)
