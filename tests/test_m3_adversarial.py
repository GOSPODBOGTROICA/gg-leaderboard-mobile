"""
Adversarial Verification & Stress Test Suite for Milestone 3
24/7 Cloud Deployment, Local LAN Launcher, QR Encoding Safety, and Container Descriptors
"""

import ast
import json
import os
import socket
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml

import run_server


REPO_ROOT = Path(__file__).resolve().parent.parent


# ==============================================================================
# 1. Adversarial LAN IP Detection Under Hostile Networking
# ==============================================================================

class TestAdversarialLanIpDetection:
    """Stress-test LAN IP auto-detection against adversarial network configurations."""

    def test_adversarial_virtual_interface_keywords_coverage(self):
        """All common VPN, hypervisor, and virtualization adapters must be flagged."""
        hostile_names = [
            "AmneziaVPN Tunnel Adapter",
            "AMNEZIA_WG",
            "OpenVPN TAP-Windows Adapter V9",
            "NordVPN Tunnel",
            "tailscale0",
            "Tailscale Tunnel",
            "ZeroTier One Virtual Port",
            "VirtualBox Host-Only Ethernet Adapter #2",
            "vboxnet0",
            "VMware Virtual Ethernet Adapter for VMnet1",
            "VMware Virtual Ethernet Adapter for VMnet8",
            "docker0",
            "docker_gwbridge",
            "veth4a82b1c",
            "tun0",
            "tap1",
            "vEthernet (WSL)",
            "Hyper-V Virtual Ethernet Adapter",
            "Bluetooth Device (Personal Area Network)",
            "Loopback Pseudo-Interface 1",
        ]
        for name in hostile_names:
            assert run_server.is_virtual_or_vpn_interface(name) is True, (
                f"Failed to identify virtual adapter: '{name}'"
            )

    def test_legitimate_physical_interface_names_preserved(self):
        """Legitimate physical interfaces must NEVER be falsely identified as virtual."""
        legitimate_names = [
            "Ethernet",
            "Ethernet 2",
            "Wi-Fi",
            "Wi-Fi 2",
            "Wireless Network Connection",
            "WLAN",
            "Local Area Connection",
            "eth0",
            "eth1",
            "en0",
            "en1",
            "wlan0",
            "Realtek Gaming 2.5GbE Family Controller",
            "Intel(R) Wi-Fi 6 AX200 160MHz",
            "Broadcom NetXtreme Gigabit Ethernet",
        ]
        for name in legitimate_names:
            assert run_server.is_virtual_or_vpn_interface(name) is False, (
                f"Falsely identified physical adapter as virtual: '{name}'"
            )

    @pytest.mark.parametrize(
        "ip, expected_blacklisted",
        [
            # Loopback
            ("127.0.0.1", True),
            ("127.0.0.2", True),
            ("127.255.255.255", True),
            # APIPA (169.254.0.0/16)
            ("169.254.0.1", True),
            ("169.254.120.35", True),
            ("169.254.255.254", True),
            # VirtualBox host-only (192.168.56.0/24)
            ("192.168.56.1", True),
            ("192.168.56.101", True),
            # Null routes & empty
            ("0.0.0.0", True),
            ("", True),
            (None, True),
            (12345, True),
            # Legitimate RFC1918 Private IPs
            ("192.168.0.1", False),
            ("192.168.0.107", False),
            ("192.168.1.1", False),
            ("192.168.55.1", False),
            ("192.168.57.1", False),
            ("10.0.0.1", False),
            ("10.100.1.50", False),
            ("172.16.0.1", False),
            ("172.31.255.254", False),
        ],
    )
    def test_adversarial_ip_blacklisting(self, ip, expected_blacklisted):
        """is_blacklisted_ip must filter loopback, APIPA, VirtualBox and bad types."""
        assert run_server.is_blacklisted_ip(ip) is expected_blacklisted

    def test_hostile_network_multihomed_priority(self):
        """
        Adversarial multi-adapter simulation:
        Adapter 1: AmneziaVPN (10.8.1.1)
        Adapter 2: VirtualBox (192.168.56.1)
        Adapter 3: WSL Hyper-V (172.28.0.1)
        Adapter 4: Docker (172.17.0.1)
        Adapter 5: Physical Wi-Fi (192.168.1.50)
        Algorithm MUST pick 192.168.1.50 and never pick a virtual adapter.
        """
        def make_mock_addr(ip, family=socket.AF_INET):
            a = MagicMock()
            a.address = ip
            a.family = family
            return a

        hostile_if_addrs = {
            "AmneziaVPN Tunnel": [make_mock_addr("10.8.1.1")],
            "VirtualBox Host-Only Ethernet Adapter": [make_mock_addr("192.168.56.1")],
            "vEthernet (WSL)": [make_mock_addr("172.28.0.1")],
            "docker0": [make_mock_addr("172.17.0.1")],
            "Wi-Fi": [
                make_mock_addr("fe80::1ff:fe23:4567:890a", socket.AF_INET6),  # IPv6
                make_mock_addr("192.168.1.50", socket.AF_INET),             # IPv4
            ],
            "Loopback Pseudo-Interface 1": [make_mock_addr("127.0.0.1")],
        }

        with patch("psutil.net_if_addrs", return_value=hostile_if_addrs):
            with patch.dict(os.environ, {}, clear=True):
                selected_ip, all_detected = run_server.get_best_lan_ip()
                assert selected_ip == "192.168.1.50"
                assert "192.168.1.50" in all_detected
                assert "10.8.1.1" in all_detected

    def test_subnet_ranking_protects_against_unmatched_virtual_adapter_name(self):
        """
        If a VPN or tunnel uses a proprietary interface name that doesn't match
        keywords (e.g. 'NordLynx' on 10.5.0.2), the RFC1918 subnet ranking
        (192.168.x.x > 10.x.x.x) still successfully selects the physical Wi-Fi IP.
        """
        def make_mock_addr(ip):
            a = MagicMock()
            a.address = ip
            a.family = socket.AF_INET
            return a

        ifaces = {
            "NordLynx": [make_mock_addr("10.5.0.2")],
            "Wi-Fi": [make_mock_addr("192.168.0.107")],
        }
        with patch("psutil.net_if_addrs", return_value=ifaces):
            with patch.dict(os.environ, {}, clear=True):
                selected_ip, _ = run_server.get_best_lan_ip()
                assert selected_ip == "192.168.0.107"

    def test_corporate_physical_lan_10_network_selected_over_vpn(self):
        """
        Corporate environment where physical interface is 10.50.1.20,
        while VPN is 10.8.0.5.
        Algorithm must select physical 10.50.1.20.
        """
        def make_mock_addr(ip):
            a = MagicMock()
            a.address = ip
            a.family = socket.AF_INET
            return a

        corporate_if_addrs = {
            "OpenVPN TAP Adapter": [make_mock_addr("10.8.0.5")],
            "Ethernet Connection": [make_mock_addr("10.50.1.20")],
        }

        with patch("psutil.net_if_addrs", return_value=corporate_if_addrs):
            with patch.dict(os.environ, {}, clear=True):
                selected_ip, _ = run_server.get_best_lan_ip()
                assert selected_ip == "10.50.1.20"

    def test_psutil_missing_or_crashing_graceful_tier_fallback(self):
        """
        When psutil raises an exception (e.g. PermissionError or missing),
        the algorithm must gracefully fall back to Tier 2 (gethostbyname_ex).
        """
        with patch("psutil.net_if_addrs", side_effect=PermissionError("Access denied")):
            with patch("socket.gethostname", return_value="myhost"):
                with patch(
                    "socket.gethostbyname_ex",
                    return_value=("myhost", [], ["192.168.10.42"]),
                ):
                    with patch.dict(os.environ, {}, clear=True):
                        selected_ip, _ = run_server.get_best_lan_ip()
                        assert selected_ip == "192.168.10.42"

    def test_completely_isolated_host_returns_loopback(self):
        """
        When all network interfaces, hostname lookups, and routing probes fail,
        algorithm must cleanly return ("127.0.0.1", ["127.0.0.1"]).
        """
        with patch("psutil.net_if_addrs", return_value={}):
            with patch("socket.gethostname", side_effect=OSError("Network down")):
                with patch("socket.socket", side_effect=OSError("Network unreachable")):
                    with patch.dict(os.environ, {}, clear=True):
                        selected_ip, all_detected = run_server.get_best_lan_ip()
                        assert selected_ip == "127.0.0.1"
                        assert all_detected == ["127.0.0.1"]

    def test_override_precedence_hierarchy(self):
        """
        Precedence order:
        CLI override > HOST_IP env > LAN_IP env > Auto-detection
        """
        # Tier 0a: CLI override beats HOST_IP
        with patch.dict(os.environ, {"HOST_IP": "10.0.0.1", "LAN_IP": "10.0.0.2"}):
            ip, _ = run_server.get_best_lan_ip(override="192.168.99.1")
            assert ip == "192.168.99.1"

        # Tier 0b: HOST_IP beats LAN_IP
        with patch.dict(os.environ, {"HOST_IP": "10.0.0.1", "LAN_IP": "10.0.0.2"}):
            ip, _ = run_server.get_best_lan_ip()
            assert ip == "10.0.0.1"

        # Tier 0c: LAN_IP used when HOST_IP is empty
        with patch.dict(os.environ, {"HOST_IP": "", "LAN_IP": "10.0.0.2"}):
            ip, _ = run_server.get_best_lan_ip()
            assert ip == "10.0.0.2"

        # Whitespace stripping in overrides
        with patch.dict(os.environ, {"HOST_IP": "   192.168.1.100  "}):
            ip, _ = run_server.get_best_lan_ip()
            assert ip == "192.168.1.100"


# ==============================================================================
# 2. Adversarial Terminal QR Code Rendering & Encoding Safety
# ==============================================================================

class TestAdversarialTerminalQrRendering:
    """Stress-test QR code generator against hostile console encodings."""

    @pytest.mark.parametrize(
        "encoding",
        ["ascii", "cp1251", "cp866", "cp1252", "cp437", "latin-1", "iso-8859-1", "utf-8"],
    )
    def test_ansi_spaces_qr_100_percent_encodable_in_hostile_encodings(self, encoding):
        """
        The fallback ANSI spaces QR code must be 100% encodable into any standard
        code page without UnicodeEncodeError.
        """
        url = "http://192.168.1.105:8000"
        ansi_qr = run_server.generate_ansi_spaces_qr(url)

        # Must not raise UnicodeEncodeError
        encoded_bytes = ansi_qr.encode(encoding)
        assert len(encoded_bytes) > 0

    def test_ansi_spaces_qr_strictly_ascii_characters(self):
        """
        Every single character in generate_ansi_spaces_qr must have an ASCII code
        point strictly below 128 (ord(c) < 128).
        """
        url = "http://192.168.1.105:8000/api/leaderboard?stake=$1&hero=MyNick"
        ansi_qr = run_server.generate_ansi_spaces_qr(url)

        non_ascii = [c for c in ansi_qr if ord(c) >= 128]
        assert len(non_ascii) == 0, f"Found non-ASCII characters in ANSI QR: {non_ascii[:10]}"

    def test_compact_qr_half_block_packing_geometry(self):
        """
        Compact half-block QR must pack 2 vertical pixels per line, cutting
        line count by ~50% compared to standard terminal QR codes.
        """
        url = "http://192.168.0.107:8000"
        compact_qr = run_server.generate_compact_qr(url)
        lines = compact_qr.splitlines()

        # Version 1 QR is 21x21 modules + 2 border = 23x23 -> 12 lines
        # Higher versions: 27x27 -> 14 lines
        assert 11 <= len(lines) <= 16, f"Compact QR line count unexpected: {len(lines)}"

        # Every line must have the identical width
        widths = {len(l) for l in lines}
        assert len(widths) == 1, f"Inconsistent line widths in compact QR: {widths}"

        # Only valid block characters are allowed
        allowed_chars = {"█", "▀", "▄", " "}
        for line in lines:
            for char in line:
                assert char in allowed_chars, f"Unexpected character '{char}' in compact QR"

    def test_render_qr_for_terminal_automatic_fallback_on_cp1251(self):
        """
        When sys.stdout has cp1251 encoding, render_qr_for_terminal must catch
        the UnicodeEncodeError on half-blocks and automatically fall back to
        ANSI spaces without crashing.
        """
        orig_stdout = sys.stdout

        class MockCp1251Stdout:
            encoding = "cp1251"

        try:
            sys.stdout = MockCp1251Stdout()
            result = run_server.render_qr_for_terminal("http://192.168.0.107:8000")

            # Must return ANSI spaces version (\033[47m background escapes)
            assert "\033[47m" in result
            assert "\033[0m" in result
            # Must encode cleanly to cp1251
            result.encode("cp1251")
        finally:
            sys.stdout = orig_stdout

    def test_render_qr_for_terminal_automatic_fallback_on_ascii(self):
        """
        When sys.stdout has strict ascii encoding, render_qr_for_terminal must
        automatically fall back to pure ASCII ANSI spaces.
        """
        orig_stdout = sys.stdout

        class MockAsciiStdout:
            encoding = "ascii"

        try:
            sys.stdout = MockAsciiStdout()
            result = run_server.render_qr_for_terminal("http://192.168.0.107:8000")

            assert "\033[47m" in result
            result.encode("ascii")
        finally:
            sys.stdout = orig_stdout

    def test_qr_generation_with_long_url_and_special_characters(self):
        """QR generators must handle long URLs with query parameters and URL encoding."""
        long_url = "http://192.168.0.107:8000/api/leaderboard?stake=%24200&hero=ChallengerNick_777&session=abcdef1234567890"
        compact = run_server.generate_compact_qr(long_url)
        ansi = run_server.generate_ansi_spaces_qr(long_url)

        assert len(compact.splitlines()) > 10
        assert len(ansi.splitlines()) > 20
        ansi.encode("cp1251")


# ==============================================================================
# 3. Adversarial Dockerfile Syntax & Instruction Validation
# ==============================================================================

class TestAdversarialDockerfileValidation:
    """Stress-test Dockerfile instructions, layer caching, and security constraints."""

    @pytest.fixture(autouse=True)
    def load_dockerfile(self):
        self.dockerfile_path = REPO_ROOT / "Dockerfile"
        assert self.dockerfile_path.is_file()
        self.content = self.dockerfile_path.read_text(encoding="utf-8")

        # Parse joined instructions
        raw_lines = [l.strip() for l in self.content.splitlines() if l.strip() and not l.strip().startswith("#")]
        joined = []
        current = ""
        for line in raw_lines:
            if line.endswith("\\"):
                current += (" " if current else "") + line[:-1].strip()
            else:
                current += (" " if current else "") + line
                joined.append(current)
                current = ""
        if current:
            joined.append(current)
        self.instructions = joined

    def test_all_dockerfile_instructions_are_valid_verbs(self):
        """Every Dockerfile command must begin with a recognized Dockerfile instruction verb."""
        valid_verbs = {
            "FROM", "MAINTAINER", "RUN", "CMD", "LABEL", "EXPOSE", "ENV",
            "ADD", "COPY", "ENTRYPOINT", "VOLUME", "USER", "WORKDIR",
            "ARG", "ONBUILD", "STOPSIGNAL", "HEALTHCHECK", "SHELL"
        }
        for instruction in self.instructions:
            verb = instruction.split()[0].upper()
            assert verb in valid_verbs, f"Invalid Dockerfile instruction: '{verb}'"

    def test_healthcheck_python_code_syntactically_valid(self):
        """
        The inline python command inside HEALTHCHECK must be syntactically valid Python
        and parseable by the Python AST without SyntaxError.
        """
        health_instruction = next(
            (i for i in self.instructions if i.startswith("HEALTHCHECK")), None
        )
        assert health_instruction is not None, "HEALTHCHECK missing from Dockerfile"

        # Extract python -c "..." string
        assert 'python -c "' in health_instruction or "python -c '" in health_instruction
        start = health_instruction.find('python -c "') + len('python -c "')
        end = health_instruction.find('"', start)
        py_snippet = health_instruction[start:end]

        # Parse with AST
        parsed = ast.parse(py_snippet)
        assert len(parsed.body) >= 1, "Healthcheck python snippet is empty"

    def test_cmd_json_array_syntax_and_shell_validity(self):
        """CMD must be a valid JSON array format and use dynamic PORT variable."""
        cmd_instruction = next((i for i in self.instructions if i.startswith("CMD")), None)
        assert cmd_instruction is not None

        json_part = cmd_instruction[len("CMD"):].strip()
        parsed_cmd = json.loads(json_part)
        assert isinstance(parsed_cmd, list)
        assert parsed_cmd[0] == "sh"
        assert parsed_cmd[1] == "-c"
        assert "${PORT:-8000}" in parsed_cmd[2] or "$PORT" in parsed_cmd[2]

    def test_security_non_root_user_ownership(self):
        """Dockerfile must ensure files are owned by appuser and runs as USER appuser."""
        user_idx = -1
        chown_idx = -1

        for idx, inst in enumerate(self.instructions):
            if "chown -R appuser:appuser" in inst:
                chown_idx = idx
            if inst.startswith("USER appuser"):
                user_idx = idx

        assert chown_idx != -1, "Dockerfile must chown /app to appuser"
        assert user_idx != -1, "Dockerfile must switch to USER appuser"
        assert chown_idx < user_idx, "chown must execute before switching to unprivileged user"


# ==============================================================================
# 4. Adversarial Cloud Blueprint & Config Parsing
# ==============================================================================

class TestAdversarialCloudDescriptors:
    """Stress-test YAML parsing, schema conformance, and configuration integrity."""

    def test_render_yaml_parses_with_strict_pyyaml_loader(self):
        """render.yaml must be 100% valid YAML and match Render Blueprint specifications."""
        render_path = REPO_ROOT / "render.yaml"
        assert render_path.is_file()
        content = render_path.read_text(encoding="utf-8")

        parsed = yaml.safe_load(content)
        assert isinstance(parsed, dict), "render.yaml root must be a YAML mapping"
        assert "services" in parsed
        assert isinstance(parsed["services"], list)
        assert len(parsed["services"]) == 1

        svc = parsed["services"][0]
        assert svc["type"] == "web"
        assert svc["runtime"] == "python"
        assert svc["plan"] == "free"
        assert "$PORT" in svc["startCommand"]
        assert svc["healthCheckPath"] == "/api/health"

        # Verify envVars structure
        env_vars = svc.get("envVars", [])
        pin_var = next((v for v in env_vars if v.get("key") == "APP_PIN"), None)
        assert pin_var is not None, "APP_PIN missing from render.yaml envVars"
        assert pin_var.get("value") == "7777"

    def test_procfile_single_line_web_process(self):
        """Procfile must define an unambiguous web process command with $PORT."""
        procfile_path = REPO_ROOT / "Procfile"
        assert procfile_path.is_file()
        content = procfile_path.read_text(encoding="utf-8").strip()

        assert content.startswith("web:")
        command = content[len("web:"):].strip()
        assert "uvicorn" in command
        assert "app.main:app" in command
        assert "$PORT" in command
        assert "--host 0.0.0.0" in command

    def test_requirements_txt_pinned_versions_and_no_duplicates(self):
        """requirements.txt must have valid package specs and no conflicting duplicate entries."""
        req_path = REPO_ROOT / "requirements.txt"
        assert req_path.is_file()
        lines = [
            l.strip()
            for l in req_path.read_text(encoding="utf-8").splitlines()
            if l.strip() and not l.strip().startswith("#")
        ]

        seen_packages = set()
        for line in lines:
            pkg_name = line.split("==")[0].split(">=")[0].split("<=")[0].split("[")[0].strip().lower()
            assert pkg_name not in seen_packages, f"Duplicate package in requirements.txt: {pkg_name}"
            seen_packages.add(pkg_name)

        # Essential runtime dependencies check
        critical_deps = {"fastapi", "uvicorn", "cryptography", "pydantic", "httpx", "qrcode", "pillow"}
        for dep in critical_deps:
            assert dep in seen_packages, f"Critical dependency '{dep}' missing from requirements.txt"

    def test_start_mobile_hud_batch_script_robustness(self):
        """START_MOBILE_HUD.bat must contain chcp 65001, error handling, and python dispatch."""
        bat_path = REPO_ROOT / "START_MOBILE_HUD.bat"
        assert bat_path.is_file()
        content = bat_path.read_text(encoding="utf-8")

        assert "chcp 65001" in content
        assert "cd /d \"%~dp0\"" in content
        assert "run_server.py %*" in content
        assert "pause" in content
        assert "setlocal enabledelayedexpansion" in content
