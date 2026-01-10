import os
import re
import json
import random
import string
import shutil

def get_random_string(length=8):
    return ''.join(random.choices(string.ascii_lowercase + string.digits, k=length))

def get_random_ip():
    return ".".join(map(str, (random.randint(1, 254) for _ in range(4))))

def get_random_port():
    return str(random.randint(1024, 65535))

def anonymize():
    source_dir = os.path.join(os.getcwd(), 'myserv')
    target_dir = os.path.join(os.getcwd(), 'demo')
    
    os.makedirs(target_dir, exist_ok=True)
    
    index_path = os.path.join(source_dir, 'index.html')
    favicon_source_dir = os.path.join(source_dir, 'favicons')
    
    if not os.path.exists(index_path):
        print(f"Error: {index_path} not found. Please run main.py first.")
        return

    with open(index_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # 1. Extract potential domains, IPs, and ports from the services JSON part
    services_match = re.search(r'var services = (\[.*?\]);', content, re.DOTALL)
    if not services_match:
        print("Error: Could not find services data in index.html.")
        return
    
    services_json = services_match.group(1)
    services = json.loads(services_json)

    # 2. Map building
    domain_map = {}
    ip_map = {}
    port_map = {}

    def map_domain(domain):
        if not domain or domain in domain_map:
            return domain_map.get(domain, domain)
        
        if 'nasnas.site' in domain:
            parts = domain.split('.')
            new_parts = []
            for p in parts:
                if p == 'nasnas' or p == 'site':
                    continue
                new_parts.append(get_random_string(6))
            new_domain = ".".join(new_parts) + ".your.com" if new_parts else "your.com"
        else:
            parts = domain.split('.')
            new_parts = [get_random_string(6) for _ in range(len(parts)-1)]
            new_parts.append(get_random_string(3))
            new_domain = ".".join(new_parts)
            
        domain_map[domain] = new_domain
        return new_domain

    def map_ip(ip):
        if not ip or ip in ip_map:
            return ip_map.get(ip, ip)
        new_ip = get_random_ip()
        ip_map[ip] = new_ip
        return new_ip

    def map_port(port):
        if not port or port in port_map:
            return port_map.get(port, port)
        new_port = get_random_port()
        port_map[port] = new_port
        return new_port

    ip_regex = r'\b(?:\d{1,3}\.){3}\d{1,3}\b'
    
    # Extract data to initialize map
    all_ips = set(re.findall(ip_regex, content))
    for ip in all_ips:
        map_ip(ip)

    for s in services:
        domain = s.get('domain')
        if domain:
            if ':' in domain:
                d_part, p_part = domain.split(':')
                map_domain(d_part)
                map_port(p_part)
            else:
                map_domain(domain)
        
        addr = s.get('internal_addr', '')
        m = re.match(r'https?://([^:/]+)(?::(\d+))?', addr)
        if m:
            host = m.group(1)
            port = m.group(2)
            if re.match(ip_regex, host):
                map_ip(host)
            else:
                map_domain(host)
            if port:
                map_port(port)

    # 3. Handle Icons
    target_favicon_dir = os.path.join(target_dir, 'favicons')
    if os.path.exists(target_favicon_dir):
        shutil.rmtree(target_favicon_dir)
    
    if os.path.exists(favicon_source_dir):
        shutil.copytree(favicon_source_dir, target_favicon_dir)
        
        # Rename copied files
        sorted_domains = sorted(domain_map.keys(), key=len, reverse=True)
        for f in os.listdir(target_favicon_dir):
            for old_d in sorted_domains:
                if old_d in f:
                    new_d = domain_map[old_d]
                    old_path = os.path.join(target_favicon_dir, f)
                    new_path = os.path.join(target_favicon_dir, f.replace(old_d, new_d))
                    if not os.path.exists(new_path):
                        os.rename(old_path, new_path)
                    break

    # 4. Perform replacements and save
    def multi_replace(text):
        for old, new in ip_map.items():
            text = text.replace(old, new)
        for old, new in domain_map.items():
            text = text.replace(old, new)
        for old, new in port_map.items():
            text = re.sub(f':{old}(?=[^\\d])', f':{new}', text)
            text = re.sub(f':{old}$', f':{new}', text)
        return text

    new_content = multi_replace(content).replace('nasnas.site', 'your.com')
    with open(os.path.join(target_dir, 'index.html'), 'w', encoding='utf-8') as f:
        f.write(new_content)

    # Handle services.json
    json_source_path = os.path.join(source_dir, 'services.json')
    if os.path.exists(json_source_path):
        with open(json_source_path, 'r', encoding='utf-8') as f:
            j_data = f.read()
        new_j_data = multi_replace(j_data).replace('nasnas.site', 'your.com')
        with open(os.path.join(target_dir, 'services.json'), 'w', encoding='utf-8') as f:
            f.write(new_j_data)

    print(f"Anonymization complete. Results saved in: {target_dir}")
    print(f"Mapped {len(domain_map)} domains, {len(ip_map)} IPs, {len(port_map)} ports.")

if __name__ == "__main__":
    anonymize()
