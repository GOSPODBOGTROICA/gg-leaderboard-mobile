#!/usr/bin/env python3
"""
GGPoker Spin & Gold Mobile Leaderboard HUD — Local LAN Launcher

Features:
- Multi-tier LAN IP auto-detection that filters VPN/virtual adapters (AmneziaVPN, VirtualBox, WSL)
- Compact 14-line terminal QR code with cp1251 UnicodeEncodeError resilience
- Modern startup banner with mobile URL and PIN reminder
- Launches uvicorn on 0.0.0.0 with port from config.json or environment
"""

import argparse
import os
import socket
import sys
from typing import List, Optional, Tuple

# Ensure stdout uses UTF-8 where supported to prevent Windows cp1251 UnicodeEncodeError
if sys.platform == "win32":
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass
    try:
        import colorama
        colorama.init()
    except ImportError:
        pass


# Common substrings identifying virtual, VPN, or container network interfaces
VIRTUAL_IFACE_KEYWORDS = [
    "vpn", "virtualbox", "vbox", "vmware", "docker", "veth",
    "tap", "tun", "amnezia", "tailscale", "zerotier", "loopback",
    "wsl", "hyper-v", "bluetooth", "pseudo"
]


def is_virtual_or_vpn_interface(name: str) -> bool:
    """Return True if interface name suggests a virtual, container, or VPN adapter."""
    name_lower = name.lower()
    return any(keyword in name_lower for keyword in VIRTUAL_IFACE_KEYWORDS)


def is_blacklisted_ip(ip: str) -> bool:
    """
    Return True if IP address is loopback, APIPA, or a well-known virtual adapter subnet.
    """
    if not ip or not isinstance(ip, str):
        return True
    # Loopback (127.0.0.0/8)
    if ip.startswith("127."):
        return True
    # APIPA / Link-local (169.254.0.0/16)
    if ip.startswith("169.254."):
        return True
    # VirtualBox default host-only network (192.168.56.0/24)
    if ip.startswith("192.168.56."):
        return True
    # Null route
    if ip == "0.0.0.0":
        return True
    return False


def get_best_lan_ip(override: Optional[str] = None) -> Tuple[str, List[str]]:
    """
    Multi-tier LAN IP detection algorithm.
    Explicitly filters VPN tunnels (e.g. AmneziaVPN 10.8.x.x), VirtualBox host-only
    adapters (192.168.56.x), WSL, and APIPA addresses.

    Returns:
        (selected_primary_ip, all_detected_ips)
    """
    # Tier 0: Explicit CLI or environment override
    if override and override.strip():
        val = override.strip()
        return val, [val]
    env_override = os.environ.get("HOST_IP") or os.environ.get("LAN_IP")
    if env_override and env_override.strip():
        val = env_override.strip()
        return val, [val]

    physical_candidates: List[str] = []
    virtual_candidates: List[str] = []

    # Tier 1: Detailed interface inspection via psutil (if available)
    try:
        import psutil  # type: ignore
        net_addrs = psutil.net_if_addrs()
        for iface_name, addrs in net_addrs.items():
            is_virt = is_virtual_or_vpn_interface(iface_name)
            for addr in addrs:
                if addr.family == socket.AF_INET:
                    ip = addr.address
                    if is_blacklisted_ip(ip):
                        continue
                    if is_virt:
                        virtual_candidates.append(ip)
                    else:
                        physical_candidates.append(ip)
    except Exception:
        pass

    # Preference ranking for physical candidates:
    # 1. 192.168.x.x (Standard home Wi-Fi / Ethernet)
    # 2. 10.x.x.x (Enterprise LAN / non-VPN)
    # 3. 172.16.x.x - 172.31.x.x
    for ip in physical_candidates:
        if ip.startswith("192.168."):
            return ip, physical_candidates + virtual_candidates

    for ip in physical_candidates:
        if ip.startswith("10."):
            return ip, physical_candidates + virtual_candidates

    if physical_candidates:
        return physical_candidates[0], physical_candidates + virtual_candidates

    # Tier 2: Hostname IP lookup
    try:
        hostname = socket.gethostname()
        host_ips = socket.gethostbyname_ex(hostname)[2]
        for ip in host_ips:
            if not is_blacklisted_ip(ip) and not ip.startswith("10.8."):
                return ip, [ip] + virtual_candidates
    except Exception:
        pass

    # Tier 3: UDP routing probe (caution: routes to public DNS, may pick VPN if active)
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.settimeout(0.5)
            s.connect(("8.8.8.8", 80))
            udp_ip = s.getsockname()[0]
            if not is_blacklisted_ip(udp_ip) and not udp_ip.startswith("10.8."):
                return udp_ip, [udp_ip] + virtual_candidates
    except Exception:
        pass

    # Tier 4: Fallback to localhost
    return "127.0.0.1", ["127.0.0.1"]


def generate_compact_qr(url: str, invert: bool = False) -> str:
    """
    Renders a compact terminal QR code using Unicode half-blocks (▀, ▄, █, ' ').
    Packs two vertical pixels into each character cell, cutting height from ~27 to ~14 lines.
    """
    import qrcode

    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=1,
        border=1,
    )
    qr.add_data(url)
    qr.make(fit=True)
    m = qr.get_matrix()
    h = len(m)
    w = len(m[0])

    lines: List[str] = []
    # In standard dark terminal (black background):
    # Light pixel = full block '█', Dark pixel = space ' '
    # If inverted: opposite
    for y in range(0, h, 2):
        row: List[str] = []
        for x in range(w):
            top = m[y][x]
            bot = m[y + 1][x] if (y + 1 < h) else False

            if invert:
                top = not top
                bot = not bot

            # False = white (light), True = black (dark module)
            if not top and not bot:
                row.append("█")
            elif not top and bot:
                row.append("▀")
            elif top and not bot:
                row.append("▄")
            else:
                row.append(" ")
        lines.append("".join(row))

    return "\n".join(lines)


def generate_ansi_spaces_qr(url: str, invert: bool = False) -> str:
    """
    Renders a terminal QR code using ANSI background colors and pure ASCII spaces.
    100% resilient against any Windows code page (cp1251, cp866, cp1252) without
    UnicodeEncodeError.
    """
    import qrcode

    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=1,
        border=1,
    )
    qr.add_data(url)
    qr.make(fit=True)
    m = qr.get_matrix()

    # ANSI color codes:
    # 47m = white background, 40m = black background, 0m = reset
    white_block = "\033[47m  \033[0m"
    black_block = "\033[40m  \033[0m"

    lines: List[str] = []
    for row in m:
        line_chars: List[str] = []
        for cell in row:
            # cell is True for dark module, False for light
            is_dark = (not cell) if invert else cell
            line_chars.append(black_block if is_dark else white_block)
        lines.append("".join(line_chars))

    return "\n".join(lines)


def render_qr_for_terminal(url: str) -> str:
    """
    Renders the QR code, trying compact half-blocks first, and safely falling
    back to ANSI spaces if a UnicodeEncodeError occurs on Windows.
    """
    try:
        qr_text = generate_compact_qr(url)
        # Test encode to stdout's current encoding
        encoding = getattr(sys.stdout, "encoding", "utf-8") or "utf-8"
        qr_text.encode(encoding)
        return qr_text
    except (UnicodeEncodeError, Exception):
        return generate_ansi_spaces_qr(url)


def build_startup_banner(lan_ip: str, port: int, pin: str, all_ips: List[str]) -> str:
    """Generates the startup informational banner with local and network URLs."""
    local_url = f"http://127.0.0.1:{port}"
    lan_url = f"http://{lan_ip}:{port}"
    other_ips_str = ", ".join(i for i in all_ips if i != lan_ip) or "none"

    banner = [
        "======================================================================",
        "    GGPoker Spin & Gold Mobile Leaderboard HUD — Local Server",
        "======================================================================",
        f"  * Mobile / LAN URL:  {lan_url}",
        f"  * Local PC URL:      {local_url}",
        f"  * Security Gate PIN: {pin} (configured in config.json / APP_PIN)",
        f"  * Detected Interfaces: {lan_ip} (secondary: {other_ips_str})",
        "======================================================================",
        "  Scan this QR code with your smartphone camera (same Wi-Fi):",
        "======================================================================",
    ]
    return "\n".join(banner)


def main():
    parser = argparse.ArgumentParser(
        description="Launch GGPoker Spin & Gold Mobile Leaderboard HUD on LAN"
    )
    parser.add_argument("--host", default="0.0.0.0", help="Host interface to bind (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=None, help="Port to bind (default: from config/PORT)")
    parser.add_argument("--reload", action="store_true", help="Enable auto-reload for development")
    parser.add_argument("--host-ip", type=str, default=None, help="Explicit LAN IP override for QR code")
    args = parser.parse_args()

    # Load configuration
    try:
        from app.config import get_settings
        settings = get_settings()
        port = args.port or settings.port or 8000
        pin = settings.pin or "7777"
    except Exception:
        port = args.port or int(os.environ.get("PORT", "8000"))
        pin = os.environ.get("APP_PIN", "7777")

    # Detect LAN IP
    lan_ip, all_ips = get_best_lan_ip(override=args.host_ip)
    target_url = f"http://{lan_ip}:{port}"

    # Print banner
    print(build_startup_banner(lan_ip, port, pin, all_ips))

    # Print QR Code
    try:
        print(render_qr_for_terminal(target_url))
    except Exception as e:
        print(f"  [Notice] Could not display terminal QR: {e}")
        print(f"  Please open {target_url} directly in your mobile browser.")

    print("======================================================================")
    print("  * iOS Safari:     Tap Share -> 'Add to Home Screen'")
    print("  * Android Chrome: Tap Menu (3 dots) -> 'Install App'")
    print("  Press Ctrl+C to stop the server.")
    print("======================================================================\n")

    # Launch Uvicorn
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host=args.host,
        port=port,
        reload=args.reload
    )


if __name__ == "__main__":
    main()
