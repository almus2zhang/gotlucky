import socket
import requests
from urllib.parse import urlparse

# Cloudflare Configuration (Optional)
CF_API_TOKEN = "" # Fill this if you want to use CF API

def resolve_domain(domain):
    try:
        # Standard DNS resolution
        ip = socket.gethostbyname(domain)
        return ip
    except:
        return "Unknown"

def get_favicon_url(domain):
    # Probing every domain sequentially with 3s timeouts is too slow for many domains.
    # We will prioritize Google's high-performance favicon service.
    return f"https://www.google.com/s2/favicons?domain={domain}&sz=64"

def get_mapping_type(ip):
    # This can be improved by checking official IP ranges
    # For now, we use a simple check or public info
    if ip == "Unknown": return "Direct/Hidden"
    
    # Mock check for CF/Alibaba
    # In a real scenario, you'd use a CIDR check
    # We'll label based on common patterns or just "Proxy"
    return "Cloudflare/ESA/Ali"
