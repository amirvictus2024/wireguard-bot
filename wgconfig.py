import random
import ipaddress
import uuid
from datetime import datetime, timedelta
import base64
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey
from cryptography.hazmat.primitives import serialization

# Configuration parameters
SERVER_ENDPOINT_PORT = 443
KEEPALIVE_INTERVAL = 15
CONFIG_VALIDITY_DAYS = 31

# WireGuard server configurations
SERVER_PUBLIC_KEYS = {
    'bronze': 'LsvVMyk492qBCh1PHWvMGbZ9GEILVvPRl4KL4iMPdgM=',
    'silver': 'G7y+SliDYYaNTrMbZ1wxIJcG/GlQgsfTQqrQi5nSCws=',
    'gold': 'UG/zZzCafRpYqgUG4DZieRYgQ/QAqjGvl4j78YgPJGE=',
    'diamond': 'MyQ5Io8rI0dZY6FLXDjKwZzXe+/gDuRQwPRIvBK9VyI='
}

# Helper functions for Wireguard config
def generate_private_key():
    """Generate a proper WireGuard private key using cryptography"""
    private_key = X25519PrivateKey.generate()
    private_bytes = private_key.private_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PrivateFormat.Raw,
        encryption_algorithm=serialization.NoEncryption()
    )
    return base64.b64encode(private_bytes).decode('ascii')

def generate_public_key(private_key):
    """Generate the corresponding public key from a private key"""
    try:
        # Convert base64 private key back to bytes
        private_bytes = base64.b64decode(private_key)
        # Load the private key
        x25519_private_key = X25519PrivateKey.from_private_bytes(private_bytes)
        # Get the public key
        x25519_public_key = x25519_private_key.public_key()
        # Get raw bytes and encode as base64
        public_bytes = x25519_public_key.public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw
        )
        return base64.b64encode(public_bytes).decode('ascii')
    except Exception as e:
        print(f"Error generating public key: {e}")
        # Fallback for any errors
        return SERVER_PUBLIC_KEYS.get('bronze')

def get_random_ip(cidr):
    # اگر از ماژول range استفاده شده، آن را وارد می‌کنیم
    try:
        from range import parse_ip_range
        cidr = parse_ip_range(cidr)
    except ImportError:
        # اگر ماژول موجود نباشد، خودمان پردازش می‌کنیم
        cidr = cidr.replace('"', '').replace("'", "").strip()
        
    network = ipaddress.ip_network(cidr)
    # Get a random host address from network
    host_bits = network.max_prefixlen - network.prefixlen
    if host_bits <= 0:
        return str(network.network_address)

    random_host = random.randint(1, (2 ** host_bits) - 2)
    random_ip = network.network_address + random_host
    return str(random_ip)

def generate_wireguard_config(location_type, locations):
    location = locations[location_type]

    # Generate a private key
    private_key = generate_private_key()

    # Use the correct server public key based on location_type
    public_key = generate_public_key(private_key)

    # Select a single IPv4 range as defined in range.py
    ipv4_range = location['ipv4_ranges'][0]
    ipv4_endpoint = get_random_ip(ipv4_range)

    # Generate DNS addresses (one fixed, one from range)
    dns_fixed = "78.157.42.100"
    dns_ipv4 = get_random_ip(ipv4_range)
    
    # Use the single IPv6 range if available or fallback
    if location['ipv6_ranges'] and len(location['ipv6_ranges']) > 0:
        ipv6_range = location['ipv6_ranges'][0]
        dns_ipv6 = get_random_ip(ipv6_range)
        address_ipv6_1 = get_random_ip(ipv6_range)
        address_ipv6_2 = get_random_ip(ipv6_range)
    else:
        dns_ipv6 = "2001:db8::1"
        address_ipv6_1 = "2001:db8::2"
        address_ipv6_2 = "2001:db8::3"

    # Generate addresses
    address_fixed1 = "10.202.10.10"
    address_fixed2 = "10.0.0.2/24"
    address_ipv4 = get_random_ip(ipv4_range)

    # Calculate expiry date (still needed for internal tracking)
    expiry_date = datetime.now() + timedelta(days=CONFIG_VALIDITY_DAYS)
    expiry_date_str = expiry_date.strftime("%Y-%m-%d")

    # Create config with the expiry date comment
    config = f"""[Interface]
PrivateKey = {private_key}
Address = {address_fixed1}, {address_fixed2}, {address_ipv4}, {address_ipv6_1}, {address_ipv6_2}
DNS = {dns_fixed}, {dns_ipv4}, {dns_ipv6}

[Peer]
PublicKey = {public_key}
AllowedIPs = 0.0.0.0/4, ::/5
Endpoint = {ipv4_endpoint}:{SERVER_ENDPOINT_PORT}
PersistentKeepalive = {KEEPALIVE_INTERVAL}
"""

    # Create a unique name for the config (just 8 characters)
    cool_name = ''.join(random.choices('abcdefghijklmnopqrstuvwxyz123456789', k=8))

    return {
        'config': config,
        'type': location_type,
        'name': location['name'],
        'price': location['price'],
        'filename': f"{cool_name}.conf",
        'expiry_date': expiry_date_str
    }

def get_config_caption(config_data, location_type):
    """Generate a beautiful caption for the config file"""
    location_emojis = {
        'bronze': '🥉',
        'silver': '🥈',
        'gold': '🥇',
        'diamond': '💎'
    }

    emoji = location_emojis.get(location_type, '🔰')

    caption = f"""
{emoji} *کانفیگ وایرگارد {config_data['name']}* {emoji}

📡 *مشخصات سرویس:*
🔐 نوع: {config_data['name']}
⏱️ مدت اعتبار: *{CONFIG_VALIDITY_DAYS} روز*
📆 تاریخ انقضا: {config_data['expiry_date']}

🔧 *راهنمای استفاده:*
1. اپلیکیشن وایرگارد را نصب کنید
2. فایل کانفیگ را وارد کنید
3. از بازس خود لذت ببرید

🛡️ از انتخاب شما متشکریم
"""
    return caption