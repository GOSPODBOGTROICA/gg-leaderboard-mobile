# Project: GG Leaderboard Mobile Web-HUD (PWA)

## Architecture
- **Backend**: Async Python 3 (FastAPI, Uvicorn, httpx, cryptography).
- **Security**: Single-User PIN Gate (default `7777`, `APP_PIN` env, `config.json`), token-based authentication via `Authorization: Bearer <token>` or Cookie, 401 Unauthorized on protected endpoints.
- **Upstream Data**: Live GGPoker Leaderboard API, OpenSSL EVP_BytesToKey MD5 key derivation, AES-256-CBC decryption, group discovery (~1458), 15-second TTL in-memory cache.
- **Frontend**: Vanilla Modern ES2022 + CSS3 Progressive Web App (PWA), zero build tools, <50KB payload. Dark high-contrast poker theme, 375px–430px mobile viewport optimization, standalone display mode, service worker offline shell caching.
- **Deployment & Networking**: Docker containerization (`python:3.11-slim`), Render (`render.yaml`), Railway (`Procfile`), local LAN launcher (`run_server.py`, `START_MOBILE_HUD.bat`) with multi-tier IP resolution (filtering VPN adapters) and terminal QR-code pairing.

## Feature Inventory
| # | Feature | Description | Milestone | Source |
|---|---------|-------------|-----------|--------|
| 1 | EVP Key Derivation | OpenSSL EVP_BytesToKey with MD5 for AES-256 key (32 bytes) and IV (16 bytes) | M1 | gg_api.py / Survey |
| 2 | AES-256-CBC Decryption | Decrypt AES-CBC ciphertext using cryptography.hazmat with PKCS7 unpadding | M1 | gg_api.py / Survey |
| 3 | Password Generation | Derive decryption password from HTTP response `milliseconds` header in hex | M1 | gg_api.py / Survey |
| 4 | Active Group Discovery | Probe promotion group IDs starting from 1458 with fallback scanner | M1 | gg_api.py / Survey |
| 5 | Stakes Extraction & Mapping | Parse all 9 active stakes ($0.25 to $200) and link to promotion IDs | M1 | gg_api.py / Survey |
| 6 | Upstream Leaderboard Fetch | Async HTTP fetch of Top-50 rankings with headers and error handling | M1 | gg_api.py / Survey |
| 7 | Leaderboard Parsing | Parse rank, nickname, points (as float), prizes (cash and ticket types) | M1 | gg_api.py / Survey |
| 8 | Partial Table Handling | Gracefully handle stakes with fewer than 50 players (e.g., $100, $200) | M1 | Survey |
| 9 | In-Memory TTL Cache | 15-second TTL cache with asyncio.Lock to protect GGPoker servers | M1 | ORIGINAL_REQUEST R1 |
| 10 | Hero Telemetry (pts_to_next) | Calculate point delta required to reach next higher rank | M1 | ORIGINAL_REQUEST R1 |
| 11 | Hero Telemetry (lead_over_prev) | Calculate point cushion over nearest trailing player | M1 | ORIGINAL_REQUEST R1 |
| 12 | Hero Boundary Rank #1 | Telemetry handles Rank #1 (pts_to_next = 0, lead over #2) | M1 | Survey |
| 13 | Hero Boundary Rank #50 | Telemetry handles Rank #50 (pts_to_next to #49, lead = null, bubble) | M1 | Survey |
| 14 | Hero Unranked Handling | Telemetry handles player not in Top-50 (target #50, pts needed) | M1 | Survey |
| 15 | Cutoff Countdown Math | Calculate exact seconds remaining until 08:00:00 UTC daily close | M1 | ORIGINAL_REQUEST R1 |
| 16 | Configuration Loader | Load PIN, port, host from config.json with env variable overrides | M1 | ORIGINAL_REQUEST R2 |
| 17 | Auth Token Generation | Cryptographically secure session token issuance on valid PIN | M1 | ORIGINAL_REQUEST R2 |
| 18 | POST /api/auth Endpoint | Verify PIN and return session token / set cookie | M1 | ORIGINAL_REQUEST R2 |
| 19 | Auth Dependency & Middleware | Protect /api/* endpoints with 401 Unauthorized for missing/invalid tokens | M1 | ORIGINAL_REQUEST R2 |
| 20 | GET /api/stakes Endpoint | Protected endpoint returning list of active stakes and prize pools | M1 | ORIGINAL_REQUEST R1 |
| 21 | GET /api/leaderboard Endpoint | Protected endpoint returning leaderboard Top-50 + Hero telemetry | M1 | ORIGINAL_REQUEST R1 |
| 22 | CORS & Static Files Serving | Serve static PWA assets from /static with proper MIME types | M1 | ORIGINAL_REQUEST R3 |
| 23 | PIN Lock Screen UI | High-contrast PIN pad / input overlay when unauthenticated | M2 | ORIGINAL_REQUEST R2 |
| 24 | Client Token Persistence | Store auth token in localStorage, auto-attach to API requests | M2 | ORIGINAL_REQUEST R2 |
| 25 | Auto-Logout on 401 | Detect 401 response and return to lock screen seamlessly | M2 | ORIGINAL_REQUEST R2 |
| 26 | Mobile-First Responsive Layout | 375px–430px viewport optimization with zero horizontal overflow | M2 | ORIGINAL_REQUEST R3 |
| 27 | Stake Selector Chips | Touch-friendly chip buttons for $0.25 through $200 | M2 | ORIGINAL_REQUEST R3 |
| 28 | Hero Nickname Persistence | Input field with instant auto-save to localStorage | M2 | ORIGINAL_REQUEST R3 |
| 29 | Hero Spotlight Card | Prominent card showing Rank Badge, points, prize, gap telemetry | M2 | ORIGINAL_REQUEST R3 |
| 30 | Daily Cutoff Timer Display | Live ticking countdown to 08:00 UTC with urgency styling (<1h red) | M2 | ORIGINAL_REQUEST R3 |
| 31 | Leaderboard Table View | Ranked list with badges (Gold/Silver/Bronze), points, prizes | M2 | ORIGINAL_REQUEST R3 |
| 32 | Hero Row Auto-Scroll | Highlight Hero row and auto-scroll into view on selection | M2 | ORIGINAL_REQUEST R3 |
| 33 | Auto-Refresh Toggle | Toggleable refresh intervals (15s, 30s, off) with live pulse dot | M2 | ORIGINAL_REQUEST R3 |
| 34 | Manual Pull-to-Refresh | Swipe down / refresh button for immediate on-demand update | M2 | ORIGINAL_REQUEST R3 |
| 35 | PWA manifest.json | App name, icons, theme-color #141619, background #0d0e11, standalone | M2 | ORIGINAL_REQUEST R3 |
| 36 | PWA Service Worker (sw.js) | Cache-First for shell assets, Network-Only for API | M2 | ORIGINAL_REQUEST R3 |
| 37 | App Icons (192px & 512px) | High-contrast PWA icons for home-screen installation | M2 | ORIGINAL_REQUEST R3 |
| 38 | Standalone Launch Optimization | iOS/Android web-app-capable meta tags to eliminate browser chrome | M2 | ORIGINAL_REQUEST R3 |
| 39 | Multi-Tier LAN IP Detection | Resolve reachable LAN IP while explicitly ignoring VPN/virtual NICs | M3 | ORIGINAL_REQUEST R4 |
| 40 | Terminal ASCII QR Code | Compact 2-line/half-block terminal QR code with ANSI space fallback | M3 | ORIGINAL_REQUEST R4 |
| 41 | run_server.py Launcher | Local launcher displaying pairing URL and QR code on startup | M3 | ORIGINAL_REQUEST R4 |
| 42 | START_MOBILE_HUD.bat | One-click Windows batch launcher with venv check and auto-run | M3 | ORIGINAL_REQUEST R4 |
| 43 | Dockerfile | Multi-stage / lightweight python:3.11-slim container with $PORT | M3 | ORIGINAL_REQUEST R4 |
| 44 | render.yaml Configuration | Infrastructure-as-code descriptor for 24/7 Render Web Service | M3 | ORIGINAL_REQUEST R4 |
| 45 | Railway Procfile | Procfile defining web worker command for Railway deployment | M3 | ORIGINAL_REQUEST R4 |
| 46 | README_DEPLOY.md Guide | 1-minute step-by-step deployment guide for Render and Railway | M3 | ORIGINAL_REQUEST R4 |
| 47 | requirements.txt | Fully specified dependency manifest | M3 | ORIGINAL_REQUEST R4 |
| 48 | Automated Pytest Suite | Test suite verifying crypto, security, telemetry, API, and PWA | M4 | ORIGINAL_REQUEST AC |

## Milestones
| # | Name | Scope | Dependencies | Status |
|---|------|-------|-------------|--------|
| M1 | Backend Engine & Security API | FastAPI application, crypto, GG client, caching, telemetry, auth gate (`app/`, `config.json`) | None | DONE |
| M2 | Mobile-First UI & PWA Frontend | Dark mobile UI, lock screen, Hero spotlight card, table, PWA assets (`static/`) | M1 | DONE |
| M3 | 24/7 Cloud Deployment & LAN Launcher | Dockerfile, render.yaml, Procfile, run_server.py, QR code, batch launcher, README_DEPLOY.md | M1, M2 | DONE |
| M4 | Comprehensive Pytest Suite & E2E Validation | Unit, integration, security, and edge-case test suite with 100% pass rate (`tests/`) | M1, M2, M3 | DONE |

## Interface Contracts
### M1 (Backend API) ↔ M2 (PWA Frontend)
- `POST /api/auth`
  - Request: `{"pin": "7777"}`
  - Response 200: `{"token": "<secure_random_hex>", "expires_in": 2592000}`
  - Response 401: `{"detail": "Invalid PIN"}`
- `GET /api/stakes`
  - Header: `Authorization: Bearer <token>`
  - Response 200: `{"stakes": [{"name": "$1", "group_id": 1458, "promotion_id": 230919, "prize_pool": "$5,000"}]}`
  - Response 401: `{"detail": "Unauthorized"}`
- `GET /api/leaderboard?stake=$1&hero=MyNick`
  - Header: `Authorization: Bearer <token>`
  - Response 200:
    ```json
    {
      "stake": "$1",
      "updated_at": "2026-10-13T01:15:00Z",
      "cutoff_seconds": 24300,
      "players": [{"rank": 1, "nickname": "Player1", "points": 1450.5, "prize": {"type": "TICKET", "text": "$50 Ticket"}}],
      "hero": {
        "found": true,
        "rank": 4,
        "nickname": "MyNick",
        "points": 920.0,
        "prize": {"type": "TICKET", "text": "$10 Ticket"},
        "pts_to_next": 45.0,
        "lead_over_prev": 60.5,
        "target_rank": 3,
        "target_prize": {"type": "TICKET", "text": "$20 Ticket"}
      }
    }
    ```

## Code Layout
```
d:\PROJECTS_ALL\MODERN_MODEL_7\GG_LEADERBOARD_MOBILE\
├── app/
│   ├── __init__.py
│   ├── main.py              # FastAPI app definition, middleware, routes, static mount
│   ├── config.py            # PIN resolution, settings, environment overrides
│   ├── auth.py              # Security gate, token generation, 401 verification
│   ├── crypto.py            # EVP_BytesToKey, AES-256-CBC decryption, PKCS7
│   ├── gg_client.py         # Async GGPoker API client, group discovery, 15s TTL cache
│   ├── telemetry.py         # Hero delta math (pts_to_next, lead_over_prev, ranks #1/#50/unranked)
│   └── models.py            # Pydantic schemas for requests, responses, telemetry
├── static/
│   ├── index.html           # Single-page mobile HUD HTML
│   ├── css/
│   │   └── style.css        # Mobile-first dark poker theme (375px-430px)
│   ├── js/
│   │   └── app.js           # Vanilla ES2022 frontend logic, auth, auto-scroll, refresh
│   ├── manifest.json        # PWA manifest
│   ├── sw.js                # Service Worker
│   └── icons/
│       ├── icon-192.png
│       └── icon-512.png
├── tests/
│   ├── conftest.py
│   ├── test_crypto.py       # AES decryption, EVP key derivation tests
│   ├── test_telemetry.py    # Hero math and edge cases (Rank 1, 50, unranked)
│   ├── test_timer.py        # 08:00 UTC countdown calculation tests
│   ├── test_security.py     # Auth gating, PIN resolution, 401 responses
│   ├── test_api.py          # FastAPI testclient endpoints verification
│   ├── test_pwa_assets.py   # Manifest and static asset presence tests
│   ├── test_telemetry_adversarial.py # Adversarial telemetry stress tests
│   ├── test_crypto_concurrency_adversarial.py # Adversarial crypto & concurrency tests
│   ├── test_m2_adversarial.py # Adversarial PWA & XSS & layout tests
│   ├── test_deployment.py   # Docker, render, procfile, LAN IP, and QR tests
│   └── test_m3_adversarial.py # Adversarial deployment & hostile networking tests
├── Dockerfile               # Containerization descriptor
├── render.yaml              # Render cloud deploy configuration
├── Procfile                 # Railway cloud deploy configuration
├── README_DEPLOY.md         # 1-minute cloud deploy instructions
├── run_server.py            # LAN launcher with QR code and IP discovery
├── START_MOBILE_HUD.bat     # Windows 1-click batch launcher
├── requirements.txt         # Dependencies
├── config.json              # Local configuration (default PIN 7777)
└── PROJECT.md               # Master architecture and feature inventory
```
