import os
import re
import configparser

def get_frp_configs(systemd_dir="/lib/systemd/system"):
    configs = []
    if not os.path.exists(systemd_dir):
        # Fallback for testing or if running on Windows (though this path is specific to Linux)
        print(f"Directory {systemd_dir} not found.")
        return configs

    # Find service files starting with frpc
    service_files = [f for f in os.listdir(systemd_dir) if f.startswith('frpc') and f.endswith('.service')]
    
    for service_file in service_files:
        path = os.path.join(systemd_dir, service_file)
        try:
            with open(path, 'r', encoding='utf-8') as f:
                content = f.read()
                # Find ExecStart to get the config file path
                # Handles multiple formats: -c path/to/config or path/to/config
                match = re.search(r'ExecStart=.*? (-c\s+|)([^\s\n]+)', content)
                if match:
                    config_path = match.group(2).strip()
                    if os.path.exists(config_path):
                        configs.append({
                            'service': service_file,
                            'config_path': config_path
                        })
                    else:
                        print(f"[!] Found config path {config_path} but it does not exist.")
        except Exception as e:
            print(f"Error reading {service_file}: {e}")
            
    return configs

def parse_frp_config(config_path):
    mappings = []
    if not os.path.exists(config_path):
        return mappings

    config_filename = os.path.basename(config_path)
    try:
        # Check if it's TOML (v0.52.0+)
        is_toml = False
        with open(config_path, 'r', encoding='utf-8') as f:
            content_sample = f.read(2048) # Read a sample
            # FRPC TOML 常见的特征是包含 [[proxies]] 或以 .toml 结尾
            if '[[proxies]]' in content_sample or config_path.endswith('.toml'):
                is_toml = True
        
        if is_toml:
            # Simple TOML parser logic for proxy definitions
            with open(config_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Extract common server_addr
            server_addr = "unknown"
            server_match = re.search(r'serverAddr\s*=\s*"([^"]+)"', content)
            if server_match: server_addr = server_match.group(1)
            
            # Find proxies [[proxies]]
            proxy_blocks = re.findall(r'\[\[proxies\]\](.*?)(?=\[\[proxies\]\]|$)', content, re.DOTALL)
            for block in proxy_blocks:
                name_m = re.search(r'name\s*=\s*"([^"]+)"', block)
                lip_m = re.search(r'localIP\s*=\s*"([^"]+)"', block)
                lport_m = re.search(r'localPort\s*=\s*(\d+)', block)
                rport_m = re.search(r'remotePort\s*=\s*(\d+)', block)
                if lport_m and rport_m:
                    mappings.append({
                        'name': name_m.group(1) if name_m else "unnamed",
                        'local_ip': lip_m.group(1) if lip_m else "127.0.0.1",
                        'local_port': lport_m.group(1),
                        'remote_port': rport_m.group(1),
                        'server_addr': server_addr,
                        'source_file': config_filename
                    })
        else:
            # INI parser
            config = configparser.ConfigParser()
            config.read(config_path)
            server_addr = config.get('common', 'server_addr', fallback='unknown')
            
            for section in config.sections():
                if section == 'common': continue
                local_ip = config.get(section, 'local_ip', fallback='127.0.0.1')
                local_port = config.get(section, 'local_port', fallback=None)
                remote_port = config.get(section, 'remote_port', fallback=None)
                if local_port and remote_port:
                    mappings.append({
                        'name': section,
                        'local_ip': local_ip,
                        'local_port': local_port,
                        'remote_port': remote_port,
                        'server_addr': server_addr,
                        'source_file': config_filename
                    })
    except Exception as e:
        print(f"Error parsing config {config_path}: {e}")
        
    return mappings

if __name__ == "__main__":
    # Test logic
    print("FRP Scanner testing...")
