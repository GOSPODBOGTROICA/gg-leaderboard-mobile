"""
Unit, integration, and security verification tests for Milestone 2:
- PWA assets and static file serving via FastAPI TestClient
- Manifest schema validation according to W3C Web App Manifest standard
- Service Worker caching strategy (Cache-First shell, Network-Only API)
- Mobile-first responsiveness, touch targets, and zero horizontal overflow
- Single-User PIN Lock overlay & UI security / XSS defenses
"""

import json
from pathlib import Path
from PIL import Image
import io
import re
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.config import get_settings

client = TestClient(app)

def test_root_serves_index_html():
    """Verify GET / returns index.html with 200 OK and expected HTML elements."""
    res = client.get("/")
    assert res.status_code == 200
    assert "text/html" in res.headers.get("content-type", "")
    content = res.text
    
    # Verify DOCTYPE and mobile-first meta
    assert "<!DOCTYPE html>" in content
    assert 'name="viewport"' in content
    assert "width=device-width" in content
    assert "viewport-fit=cover" in content
    
    # Verify PWA meta tags
    assert 'name="theme-color" content="#141619"' in content
    assert 'name="apple-mobile-web-app-capable" content="yes"' in content
    assert 'rel="manifest" href="/static/manifest.json"' in content
    
    # Verify Core UI Components
    assert 'id="pulse-dot"' in content
    assert 'id="countdown-pill"' in content
    assert 'id="countdown-timer-text"' in content
    assert 'id="btn-logout"' in content
    assert 'id="stake-chips-scroll"' in content
    assert 'id="hero-input"' in content
    assert 'id="refresh-interval"' in content
    assert 'id="btn-refresh"' in content
    assert 'id="hero-spotlight-card"' in content
    assert 'id="spotlight-rank-badge"' in content
    assert 'id="spotlight-pts-next"' in content
    assert 'id="spotlight-cushion"' in content
    assert 'id="leaderboard-list"' in content
    assert 'id="pin-lock-overlay"' in content
    assert 'id="pin-modal-card"' in content

def test_static_index_html_direct():
    """Verify GET /static/index.html is served directly via static files mount."""
    res = client.get("/static/index.html")
    assert res.status_code == 200
    assert "text/html" in res.headers.get("content-type", "")
    assert "GG Leaderboard Mobile HUD" in res.text

def test_static_css_style():
    """Verify GET /static/css/style.css is served and contains poker theme styles."""
    res = client.get("/static/css/style.css")
    assert res.status_code == 200
    assert "text/css" in res.headers.get("content-type", "")
    css = res.text
    
    # Verify color tokens
    assert "--bg-base: #0d0e11;" in css
    assert "--bg-card: #141619;" in css
    assert "--gold: #e5a93c;" in css
    assert "--green: #00e676;" in css
    assert "--danger: #ff5252;" in css
    assert "--hero-accent: #3b82f6;" in css
    
    # Verify zero horizontal overflow & mobile responsive rules
    assert "overflow-x: hidden;" in css
    assert "max-width: 480px;" in css
    assert "safe-area-inset" in css

def test_static_js_app():
    """Verify GET /static/js/app.js is served and contains frontend logic."""
    res = client.get("/static/js/app.js")
    assert res.status_code == 200
    js = res.text
    
    # Verify token storage and auth gate
    assert "gg_hud_token" in js
    assert "Authorization" in js
    assert "Bearer" in js
    assert "/api/auth" in js
    assert "/api/leaderboard" in js
    assert "/api/stakes" in js
    
    # Verify features: timer, service worker, auto-scroll
    assert "countdownTimerText" in js
    assert "scrollIntoView" in js
    assert "serviceWorker" in js

def test_static_manifest_json():
    """Verify GET /static/manifest.json returns valid PWA specification."""
    res = client.get("/static/manifest.json")
    assert res.status_code == 200
    
    data = res.json()
    assert data["name"] == "GGPoker Spin & Gold Leaderboard HUD"
    assert data["short_name"] == "GG HUD"
    assert data["start_url"] == "/"
    assert data["display"] == "standalone"
    assert data["background_color"] == "#0d0e11"
    assert data["theme_color"] == "#141619"
    
    # Validate icons array
    icons = data.get("icons", [])
    assert len(icons) >= 2
    
    sizes = [ic.get("sizes") for ic in icons]
    assert "192x192" in sizes
    assert "512x512" in sizes
    
    for ic in icons:
        assert ic.get("type") == "image/png"
        assert "src" in ic

def test_static_sw_js():
    """Verify GET /static/sw.js serves service worker with Cache-First & Network-Only rules."""
    res = client.get("/static/sw.js")
    assert res.status_code == 200
    sw = res.text
    
    # Verify Cache-First and Network-Only rules
    assert "CACHE_NAME" in sw
    assert "/api/" in sw
    assert "fetch(request)" in sw
    assert "caches.match" in sw

def test_static_icons_png_validity():
    """Verify both 192px and 512px PNG icons exist, are valid PNGs, and match dimensions."""
    # Test icon-192.png
    res_192 = client.get("/static/icons/icon-192.png")
    assert res_192.status_code == 200
    assert "image/png" in res_192.headers.get("content-type", "")
    assert res_192.content.startswith(b"\x89PNG\r\n\x1a\n")
    
    img_192 = Image.open(io.BytesIO(res_192.content))
    assert img_192.size == (192, 192)
    assert img_192.format == "PNG"

    # Test icon-512.png
    res_512 = client.get("/static/icons/icon-512.png")
    assert res_512.status_code == 200
    assert "image/png" in res_512.headers.get("content-type", "")
    assert res_512.content.startswith(b"\x89PNG\r\n\x1a\n")
    
    img_512 = Image.open(io.BytesIO(res_512.content))
    assert img_512.size == (512, 512)
    assert img_512.format == "PNG"

def test_pwa_manifest_icon_assets_exist():
    """Verify all icon files declared in manifest.json actually resolve via HTTP."""
    res_manifest = client.get("/static/manifest.json")
    assert res_manifest.status_code == 200
    manifest = res_manifest.json()
    
    for icon_decl in manifest.get("icons", []):
        src = icon_decl.get("src")
        assert src is not None
        icon_res = client.get(src)
        assert icon_res.status_code == 200, f"Declared icon {src} failed to load (status {icon_res.status_code})"

def test_offline_shell_cached_assets_exist():
    """Verify all static assets registered in service worker cache list exist on disk."""
    static_dir = get_settings().static_dir
    assert static_dir.is_dir()
    
    expected_files = [
        "index.html",
        "css/style.css",
        "js/app.js",
        "manifest.json",
        "icons/icon-192.png",
        "icons/icon-512.png"
    ]
    for rel_path in expected_files:
        target = static_dir / rel_path
        assert target.is_file(), f"Missing static asset {rel_path} in {static_dir}"

def test_all_nine_stakes_present_in_html():
    """Verify all 9 Spin & Gold stakes ($0.25 to $200) are defined as touch chips in index.html."""
    res = client.get("/")
    assert res.status_code == 200
    html = res.text
    
    expected_stakes = ["$0.25", "$1", "$3", "$5", "$10", "$20", "$50", "$100", "$200"]
    for s in expected_stakes:
        assert f'data-stake="{s}"' in html, f"Missing stake chip {s} in HTML"

def test_pin_keypad_buttons_complete():
    """Verify numeric keypad contains all keys: 0-9, clear, enter."""
    res = client.get("/")
    assert res.status_code == 200
    html = res.text
    
    for digit in range(10):
        assert f'data-key="{digit}"' in html, f"Missing keypad digit {digit}"
    assert 'data-key="clear"' in html
    assert 'data-key="enter"' in html

def test_frontend_xss_protection():
    """Verify frontend code does not execute unsafe eval or inject unescaped raw HTML."""
    res = client.get("/static/js/app.js")
    assert res.status_code == 200
    js = res.text
    
    # Forbidden dangerous patterns
    assert "eval(" not in js
    assert "document.write(" not in js
    assert "innerHTML = player" not in js
    assert "innerHTML = hero" not in js
    # Safe textContent should be used
    assert ".textContent = " in js

def test_touch_target_accessibility_css():
    """Verify touch targets (chips, keypad, inputs) have accessible heights >= 44px."""
    res = client.get("/static/css/style.css")
    assert res.status_code == 200
    css = res.text
    
    # Check that minimum touch target sizes are respected
    assert "min-height: 44px;" in css or "height: 44px;" in css
    assert "height: 54px;" in css  # keypad buttons
