"""
Comprehensive Verification Test Suite for Milestone 3:
24/7 Cloud Deployment & LAN Launcher Architecture
"""

import os
import re
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
from fastapi.testclient import TestClient

from app.main import app
import run_server


REPO_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def client():
    return TestClient(app)


# ==============================================================================
# 1. Dockerfile Architecture & Syntax Verification
# ==============================================================================

class TestDockerfileArchitecture:
    """Verifies production Dockerfile container requirements and standards."""

    @pytest.fixture(autouse=True)
    def setup_dockerfile(self):
        self.dockerfile_path = REPO_ROOT / "Dockerfile"
        assert self.dockerfile_path.is_file(), "Dockerfile must exist at repository root"
        self.content = self.dockerfile_path.read_text(encoding="utf-8")
        
        # Parse Dockerfile joining multi-line backslash continuations
        raw_lines = [l.strip() for l in self.content.splitlines() if l.strip() and not l.strip().startswith("#")]
        joined_lines = []
        current = ""
        for line in raw_lines:
            if line.endswith("\\"):
                current += (" " if current else "") + line[:-1].strip()
            else:
                current += (" " if current else "") + line
                joined_lines.append(current)
                current = ""
        if current:
            joined_lines.append(current)

        self.instructions = joined_lines

    def test_base_image_python_311_slim(self):
        """Must use official lightweight python:3.11-slim base image."""
        from_lines = [l for l in self.instructions if l.startswith("FROM")]
        assert len(from_lines) >= 1, "Dockerfile must define a FROM instruction"
        assert "python:3.11-slim" in from_lines[0], f"Expected python:3.11-slim, got {from_lines[0]}"

    def test_working_directory_set_to_app(self):
        """Must set WORKDIR /app."""
        workdir_lines = [l for l in self.instructions if l.startswith("WORKDIR")]
        assert len(workdir_lines) >= 1, "Dockerfile must set WORKDIR"
        assert "/app" in workdir_lines[0]

    def test_requirements_copied_and_installed_first(self):
        """Dependencies must be copied and installed before application code for caching."""
        req_copy_idx = -1
        app_copy_idx = -1
        pip_install_idx = -1

        for i, line in enumerate(self.instructions):
            if line.startswith("COPY") and "requirements.txt" in line:
                req_copy_idx = i
            elif line.startswith("RUN") and "pip install" in line:
                pip_install_idx = i
            elif line.startswith("COPY") and ("app" in line or "static" in line):
                if app_copy_idx == -1:
                    app_copy_idx = i

        assert req_copy_idx != -1, "Dockerfile must COPY requirements.txt"
        assert pip_install_idx != -1, "Dockerfile must RUN pip install"
        assert app_copy_idx != -1, "Dockerfile must COPY app code"
        assert req_copy_idx < pip_install_idx < app_copy_idx, (
            "requirements.txt must be copied and installed before application code to leverage Docker layer caching"
        )

    def test_unprivileged_user_configured(self):
        """Production security requires running under an unprivileged user."""
        user_lines = [l for l in self.instructions if l.startswith("USER")]
        assert len(user_lines) >= 1, "Dockerfile must declare an unprivileged USER"
        assert "appuser" in user_lines[0] or "1000" in user_lines[0]

    def test_port_exposure_and_healthcheck(self):
        """Dockerfile must EXPOSE port and define a HEALTHCHECK."""
        expose_lines = [l for l in self.instructions if l.startswith("EXPOSE")]
        health_lines = [l for l in self.instructions if l.startswith("HEALTHCHECK")]
        assert len(expose_lines) >= 1, "Dockerfile must EXPOSE a port"
        assert len(health_lines) >= 1, "Dockerfile must define a HEALTHCHECK"
        assert "/api/health" in health_lines[0]

    def test_cmd_uvicorn_dynamic_port_binding(self):
        """CMD must execute uvicorn on 0.0.0.0 using dynamic $PORT variable and exec for signals."""
        cmd_lines = [l for l in self.instructions if l.startswith("CMD")]
        assert len(cmd_lines) == 1, "Dockerfile must have exactly one active CMD"
        cmd_str = cmd_lines[0]
        assert "exec uvicorn" in cmd_str
        assert "app.main:app" in cmd_str
        assert "0.0.0.0" in cmd_str
        assert "PORT" in cmd_str



# ==============================================================================
# 2. Cloud Platform Descriptors (render.yaml & Procfile)
# ==============================================================================

class TestCloudDeploymentDescriptors:
    """Verifies Render Blueprint and Railway Procfile definitions."""

    def test_render_yaml_validity_and_contents(self):
        """render.yaml must declare a free Python web service with correct start command."""
        render_path = REPO_ROOT / "render.yaml"
        assert render_path.is_file(), "render.yaml must exist at repository root"
        content = render_path.read_text(encoding="utf-8")

        assert "services:" in content
        assert "type: web" in content
        assert "name: gg-leaderboard-mobile" in content
        assert "runtime: python" in content
        assert "plan: free" in content
        assert "buildCommand: pip install -r requirements.txt" in content
        assert "startCommand: uvicorn app.main:app --host 0.0.0.0 --port $PORT" in content
        assert "healthCheckPath: /api/health" in content
        assert "APP_PIN" in content

    def test_procfile_validity_for_railway_and_heroku(self):
        """Procfile must declare web worker binding to $PORT."""
        procfile_path = REPO_ROOT / "Procfile"
        assert procfile_path.is_file(), "Procfile must exist at repository root"
        content = procfile_path.read_text(encoding="utf-8").strip()

        expected = "web: uvicorn app.main:app --host 0.0.0.0 --port $PORT"
        assert content == expected, f"Procfile content mismatch: expected '{expected}', got '{content}'"


# ==============================================================================
# 3. Dependencies & Documentation Verification
# ==============================================================================

class TestDependenciesAndDocumentation:
    """Verifies requirements.txt completeness and README_DEPLOY.md guide."""

    def test_requirements_txt_contains_all_runtime_dependencies(self):
        """requirements.txt must include all necessary libraries."""
        req_path = REPO_ROOT / "requirements.txt"
        assert req_path.is_file(), "requirements.txt must exist at repository root"
        req_text = req_path.read_text(encoding="utf-8").lower()

        required_packages = [
            "fastapi",
            "uvicorn",
            "cryptography",
            "pydantic",
            "httpx",
            "qrcode",
            "pillow",
        ]
        for pkg in required_packages:
            assert any(line.startswith(pkg) for line in req_text.splitlines()), (
                f"Required dependency '{pkg}' missing from requirements.txt"
            )

    def test_readme_deploy_comprehensive_instructions(self):
        """README_DEPLOY.md must document Render, Railway, Docker, LAN, and PWA setup."""
        readme_path = REPO_ROOT / "README_DEPLOY.md"
        assert readme_path.is_file(), "README_DEPLOY.md must exist at repository root"
        content = readme_path.read_text(encoding="utf-8")

        assert "Render.com" in content
        assert "Railway.app" in content
        assert "Docker" in content
        assert "START_MOBILE_HUD.bat" in content
        assert "APP_PIN" in content
        assert "Add to Home Screen" in content
        assert "Safari" in content
        assert "Chrome" in content

    def test_start_mobile_hud_batch_script(self):
        """START_MOBILE_HUD.bat must check Python, support UTF-8, and run run_server.py."""
        bat_path = REPO_ROOT / "START_MOBILE_HUD.bat"
        assert bat_path.is_file(), "START_MOBILE_HUD.bat must exist at repository root"
        content = bat_path.read_text(encoding="utf-8")

        assert "chcp 65001" in content
        assert "run_server.py" in content
        assert "python" in content.lower()
        assert "pause" in content
        # Ensure parentheses inside if blocks are not present to prevent cmd.exe syntax crash
        assert "(.venv)" not in content
        assert "(venv)" not in content

    def test_start_mobile_hud_batch_crlf_line_endings(self):
        """START_MOBILE_HUD.bat must strictly use binary Windows CRLF (\\r\\n) line endings."""
        bat_path = REPO_ROOT / "START_MOBILE_HUD.bat"
        assert bat_path.is_file(), "START_MOBILE_HUD.bat must exist at repository root"
        raw_bytes = bat_path.read_bytes()

        assert b"\r\n" in raw_bytes, "START_MOBILE_HUD.bat must contain CRLF (\\r\\n) line endings"
        assert raw_bytes.count(b"\r\n") == raw_bytes.count(b"\n"), (
            "START_MOBILE_HUD.bat contains bare LF line endings without preceding CR"
        )

    def test_start_mobile_hud_batch_execution_help(self):
        """
        Executing START_MOBILE_HUD.bat with --help via cmd.exe must exit with code 0
        and execute cleanly without syntax errors ('... was unexpected at this time').
        """
        bat_path = REPO_ROOT / "START_MOBILE_HUD.bat"
        assert bat_path.is_file(), "START_MOBILE_HUD.bat must exist at repository root"

        if sys.platform != "win32":
            pytest.skip("Batch execution test requires Windows cmd.exe")

        res = subprocess.run(
            ["cmd.exe", "/c", str(bat_path), "--help"],
            capture_output=True,
            text=True,
            cwd=str(REPO_ROOT),
            timeout=15,
        )

        assert res.returncode == 0, (
            f"Batch script execution failed with code {res.returncode}:\n"
            f"STDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}"
        )
        combined_output = res.stdout + res.stderr
        assert "unexpected at this time" not in combined_output, (
            f"Batch syntax error detected in output:\n{combined_output}"
        )
        assert "is not recognized as an internal or external command" not in combined_output, (
            f"Mangled command line detected in output:\n{combined_output}"
        )
        assert "usage:" in combined_output.lower() or "help" in combined_output.lower()


# ==============================================================================
# 4. LAN IP Detection & Virtual Adapter Filtering
# ==============================================================================

class TestLanIpDetectionAlgorithm:
    """Verifies that VPN/virtual adapters are filtered and physical LAN IPs are resolved."""

    def test_virtual_interface_keyword_matching(self):
        """Must identify VPN, VirtualBox, WSL, Docker, and container adapters."""
        assert run_server.is_virtual_or_vpn_interface("AmneziaVPN") is True
        assert run_server.is_virtual_or_vpn_interface("VirtualBox Host-Only Network") is True
        assert run_server.is_virtual_or_vpn_interface("vboxnet0") is True
        assert run_server.is_virtual_or_vpn_interface("docker0") is True
        assert run_server.is_virtual_or_vpn_interface("veth12345") is True
        assert run_server.is_virtual_or_vpn_interface("tailscale0") is True
        assert run_server.is_virtual_or_vpn_interface("tun0") is True
        assert run_server.is_virtual_or_vpn_interface("tap0") is True
        assert run_server.is_virtual_or_vpn_interface("WSL (Hyper-V firewall)") is True
        assert run_server.is_virtual_or_vpn_interface("Loopback Pseudo-Interface 1") is True

        # Physical interfaces must NOT be flagged
        assert run_server.is_virtual_or_vpn_interface("Ethernet 2") is False
        assert run_server.is_virtual_or_vpn_interface("Wi-Fi") is False
        assert run_server.is_virtual_or_vpn_interface("WLAN") is False
        assert run_server.is_virtual_or_vpn_interface("en0") is False
        assert run_server.is_virtual_or_vpn_interface("eth0") is False

    def test_blacklisted_ip_filtering(self):
        """Must filter loopback, APIPA, and VirtualBox default subnets."""
        assert run_server.is_blacklisted_ip("127.0.0.1") is True
        assert run_server.is_blacklisted_ip("127.0.1.1") is True
        assert run_server.is_blacklisted_ip("169.254.80.199") is True
        assert run_server.is_blacklisted_ip("192.168.56.1") is True
        assert run_server.is_blacklisted_ip("0.0.0.0") is True
        assert run_server.is_blacklisted_ip("") is True

        # Legitimate LAN IPs must NOT be blacklisted
        assert run_server.is_blacklisted_ip("192.168.0.107") is False
        assert run_server.is_blacklisted_ip("192.168.1.1") is False
        assert run_server.is_blacklisted_ip("10.0.0.5") is False
        assert run_server.is_blacklisted_ip("172.16.0.10") is False

    def test_explicit_override_precedence(self):
        """CLI or argument override takes top priority."""
        ip, all_ips = run_server.get_best_lan_ip(override="192.168.1.250")
        assert ip == "192.168.1.250"
        assert all_ips == ["192.168.1.250"]

    def test_environment_variable_override_precedence(self):
        """HOST_IP environment variable overrides detection."""
        with patch.dict(os.environ, {"HOST_IP": "10.0.4.88"}):
            ip, all_ips = run_server.get_best_lan_ip()
            assert ip == "10.0.4.88"
            assert all_ips == ["10.0.4.88"]

    def test_psutil_simulated_network_interface_selection(self):
        """
        Simulate real host condition: AmneziaVPN (10.8.1.1), VirtualBox (192.168.56.1),
        and physical Ethernet (192.168.0.107). Algorithm must pick 192.168.0.107.
        """
        import socket
        Addr = MagicMock()
        Addr.family = socket.AF_INET

        def make_addr(ip):
            a = MagicMock()
            a.family = socket.AF_INET
            a.address = ip
            return a

        mock_if_addrs = {
            "AmneziaVPN": [make_addr("10.8.1.1")],
            "VirtualBox Host-Only Network": [make_addr("192.168.56.1")],
            "Ethernet 2": [make_addr("192.168.0.107")],
            "Loopback Pseudo-Interface 1": [make_addr("127.0.0.1")],
        }

        with patch("psutil.net_if_addrs", return_value=mock_if_addrs):
            with patch.dict(os.environ, {}, clear=True):
                ip, all_ips = run_server.get_best_lan_ip()
                assert ip == "192.168.0.107"
                assert "10.8.1.1" in all_ips
                assert "192.168.0.107" in all_ips

    def test_fallback_when_no_physical_interfaces(self):
        """When all interfaces are virtual/loopback, falls back cleanly."""
        with patch("psutil.net_if_addrs", return_value={}):
            with patch("socket.gethostbyname_ex", side_effect=Exception("mock")):
                with patch("socket.socket", side_effect=Exception("mock")):
                    with patch.dict(os.environ, {}, clear=True):
                        ip, all_ips = run_server.get_best_lan_ip()
                        assert ip == "127.0.0.1"


# ==============================================================================
# 5. Terminal QR Code Generation & Resilience
# ==============================================================================

class TestTerminalQrCodeGeneration:
    """Verifies compact half-block QR rendering and encoding error fallbacks."""

    def test_compact_qr_generation_dimensions(self):
        """Compact half-block QR should be roughly 14 lines high."""
        url = "http://192.168.0.107:8000"
        qr_str = run_server.generate_compact_qr(url)
        lines = qr_str.splitlines()

        assert len(lines) >= 12 and len(lines) <= 16, f"Expected ~14 lines, got {len(lines)}"
        # Check presence of Unicode half-block characters
        assert any("█" in l or "▀" in l or "▄" in l for l in lines)

    def test_ansi_spaces_qr_generation_ascii_safe(self):
        """ANSI spaces QR must contain only ASCII characters and color escapes."""
        url = "http://192.168.0.107:8000"
        ansi_qr = run_server.generate_ansi_spaces_qr(url)

        # Must contain ANSI color reset and background escapes
        assert "\033[47m" in ansi_qr or "\033[40m" in ansi_qr
        assert "\033[0m" in ansi_qr
        # Must be completely encodable in strict ASCII and cp1251
        ansi_qr.encode("ascii")
        ansi_qr.encode("cp1251")

    def test_render_qr_for_terminal_returns_valid_output(self):
        """render_qr_for_terminal should return a non-empty string."""
        url = "http://192.168.0.107:8000"
        rendered = run_server.render_qr_for_terminal(url)
        assert len(rendered) > 50

    def test_startup_banner_content(self):
        """Startup banner must display mobile LAN URL, local URL, port, and PIN."""
        banner = run_server.build_startup_banner(
            lan_ip="192.168.0.107",
            port=8000,
            pin="7777",
            all_ips=["192.168.0.107", "10.8.1.1"]
        )
        assert "http://192.168.0.107:8000" in banner
        assert "http://127.0.0.1:8000" in banner
        assert "7777" in banner
        assert "Scan this QR code" in banner


# ==============================================================================
# 6. Service Worker & Manifest Root Endpoints Verification
# ==============================================================================

class TestRootServiceWorkerAndManifestEndpoints:
    """Verifies that /sw.js and /manifest.json are accessible at root with proper headers."""

    def test_get_sw_js_root_endpoint_status_and_headers(self, client):
        """GET /sw.js must return HTTP 200, JS content-type, and Service-Worker-Allowed header."""
        res = client.get("/sw.js")
        assert res.status_code == 200
        content_type = res.headers.get("content-type", "")
        assert "javascript" in content_type or "application/x-javascript" in content_type

        # Root scope authorization header
        assert res.headers.get("service-worker-allowed") == "/"

        # Cache control header ensuring browser always revalidates service worker
        assert res.headers.get("cache-control") == "no-cache, no-store, must-revalidate"

        # Content verification
        body = res.text
        assert "CACHE_NAME" in body
        assert "STATIC_ASSETS" in body
        assert "fetch" in body
        assert "/api/" in body

    def test_get_manifest_json_root_endpoint(self, client):
        """GET /manifest.json must return HTTP 200 and valid PWA manifest JSON."""
        res = client.get("/manifest.json")
        assert res.status_code == 200
        data = res.json()

        assert "name" in data
        assert data.get("display") == "standalone"
        assert "theme_color" in data
        assert "icons" in data
        assert len(data["icons"]) >= 2

    def test_backward_compatibility_static_endpoints(self, client):
        """GET /static/sw.js and /static/manifest.json must continue to work."""
        res_sw = client.get("/static/sw.js")
        assert res_sw.status_code == 200

        res_manifest = client.get("/static/manifest.json")
        assert res_manifest.status_code == 200
