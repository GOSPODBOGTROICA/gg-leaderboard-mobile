/**
 * GGPoker Spin & Gold Mobile Leaderboard HUD
 * Vanilla ES2022 Mobile-First Frontend Application
 */

(() => {
  'use strict';

  // --- Constants & Storage Keys ---
  const STORAGE_KEY_TOKEN = 'gg_hud_token';
  const STORAGE_KEY_STAKE = 'gg_hud_stake';
  const STORAGE_KEY_HERO = 'gg_hud_hero';
  const STORAGE_KEY_REFRESH = 'gg_hud_refresh';

  const DEFAULT_STAKE = '$0.25';
  const DEFAULT_REFRESH = '15';

  // --- Application State ---
  const state = {
    token: localStorage.getItem(STORAGE_KEY_TOKEN) || null,
    stake: localStorage.getItem(STORAGE_KEY_STAKE) || DEFAULT_STAKE,
    heroNick: (localStorage.getItem(STORAGE_KEY_HERO) || '').trim(),
    refreshIntervalSec: parseInt(localStorage.getItem(STORAGE_KEY_REFRESH) || DEFAULT_REFRESH, 10),
    
    // Telemetry & Cutoff
    targetCutoffMs: null,
    timerIntervalId: null,
    refreshTimerId: null,
    isFetching: false,
    
    // PIN pad buffer
    pinBuffer: '',
    
    // Touch pull-to-refresh
    touchStartY: 0,
    isPulling: false
  };

  // --- DOM Elements ---
  const el = {
    // Header
    pulseDot: document.getElementById('pulse-dot'),
    countdownPill: document.getElementById('countdown-pill'),
    countdownTimerText: document.getElementById('countdown-timer-text'),
    btnLogout: document.getElementById('btn-logout'),

    // Stake chips
    stakeChipsScroll: document.getElementById('stake-chips-scroll'),
    stakeChips: document.querySelectorAll('.stake-chip'),

    // Hero controls
    heroInput: document.getElementById('hero-input'),
    heroClear: document.getElementById('hero-clear'),
    refreshSelect: document.getElementById('refresh-interval'),
    btnRefresh: document.getElementById('btn-refresh'),
    pullIndicator: document.getElementById('pull-indicator'),

    // Spotlight card
    spotlightCard: document.getElementById('hero-spotlight-card'),
    spotlightRankBadge: document.getElementById('spotlight-rank-badge'),
    spotlightNick: document.getElementById('spotlight-nick'),
    spotlightStake: document.getElementById('spotlight-stake'),
    spotlightPrize: document.getElementById('spotlight-prize'),
    spotlightPoints: document.getElementById('spotlight-points'),
    spotlightPtsNext: document.getElementById('spotlight-pts-next'),
    spotlightCushion: document.getElementById('spotlight-cushion'),
    spotlightDangerBanner: document.getElementById('spotlight-danger-banner'),
    dangerBannerText: document.getElementById('danger-banner-text'),

    // Table
    tableTitle: document.getElementById('table-title'),
    prizePoolBadge: document.getElementById('prize-pool-badge'),
    leaderboardList: document.getElementById('leaderboard-list'),

    // PIN Lock Overlay
    pinOverlay: document.getElementById('pin-lock-overlay'),
    pinModalCard: document.getElementById('pin-modal-card'),
    pinHiddenInput: document.getElementById('pin-hidden-input'),
    pinError: document.getElementById('pin-error'),
    pinDots: [
      document.getElementById('dot-0'),
      document.getElementById('dot-1'),
      document.getElementById('dot-2'),
      document.getElementById('dot-3')
    ],
    pinButtons: document.querySelectorAll('.pin-btn'),

    // Toast
    toastNotice: document.getElementById('toast-notice')
  };

  // ==========================================================================
  // Toast & UI Feedback Helpers
  // ==========================================================================
  let toastTimeout = null;
  function showToast(message, duration = 3000) {
    if (!el.toastNotice) return;
    el.toastNotice.textContent = message;
    el.toastNotice.classList.add('visible');
    clearTimeout(toastTimeout);
    toastTimeout = setTimeout(() => {
      el.toastNotice.classList.remove('visible');
    }, duration);
  }

  function setPulseState(status) {
    if (!el.pulseDot) return;
    el.pulseDot.className = 'pulse-dot';
    if (status === 'syncing') {
      el.pulseDot.classList.add('syncing');
    } else if (status === 'error') {
      el.pulseDot.classList.add('error');
    }
  }

  // ==========================================================================
  // PIN Pad & Authentication Gate
  // ==========================================================================
  function showLockScreen() {
    state.pinBuffer = '';
    updatePinDots();
    if (el.pinError) el.pinError.textContent = '';
    if (el.pinOverlay) el.pinOverlay.classList.remove('hidden');
    if (el.pinHiddenInput) el.pinHiddenInput.focus();
  }

  function hideLockScreen() {
    state.pinBuffer = '';
    updatePinDots();
    if (el.pinOverlay) el.pinOverlay.classList.add('hidden');
  }

  function updatePinDots() {
    const len = state.pinBuffer.length;
    el.pinDots.forEach((dot, idx) => {
      if (idx < len) {
        dot.classList.add('filled');
      } else {
        dot.classList.remove('filled');
      }
    });
  }

  function triggerPinError(msg) {
    if (el.pinError) el.pinError.textContent = msg;
    if (el.pinModalCard) {
      el.pinModalCard.classList.remove('shake');
      // Trigger reflow for re-triggering animation
      void el.pinModalCard.offsetWidth;
      el.pinModalCard.classList.add('shake');
    }
    state.pinBuffer = '';
    updatePinDots();
  }

  async function submitPin(pinCode) {
    if (!pinCode || pinCode.length < 1) {
      triggerPinError('Please enter PIN');
      return;
    }

    setPulseState('syncing');
    try {
      const response = await fetch('/api/auth', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ pin: pinCode })
      });

      if (!response.ok) {
        const data = await response.json().catch(() => ({}));
        triggerPinError(data.detail || 'Invalid PIN code');
        setPulseState('error');
        return;
      }

      const data = await response.json();
      if (data.token) {
        state.token = data.token;
        localStorage.setItem(STORAGE_KEY_TOKEN, state.token);
        hideLockScreen();
        showToast('HUD Unlocked');
        setPulseState('idle');
        fetchLeaderboardData();
      } else {
        triggerPinError('Authentication error');
      }
    } catch (err) {
      triggerPinError('Network connection error');
      setPulseState('error');
    }
  }

  function handleKeypadPress(key) {
    if (key === 'clear') {
      state.pinBuffer = '';
      if (el.pinError) el.pinError.textContent = '';
      updatePinDots();
    } else if (key === 'enter') {
      submitPin(state.pinBuffer);
    } else if (/^[0-9]$/.test(key)) {
      if (state.pinBuffer.length < 8) {
        state.pinBuffer += key;
        updatePinDots();
        if (el.pinError) el.pinError.textContent = '';
        if (state.pinBuffer.length === 4) {
          // Auto-submit on 4 digits for fast mobile access
          submitPin(state.pinBuffer);
        }
      }
    }
  }

  function logout() {
    state.token = null;
    localStorage.removeItem(STORAGE_KEY_TOKEN);
    showToast('HUD Locked');
    showLockScreen();
  }

  // ==========================================================================
  // HTTP Fetch Wrapper with 401 Interceptor
  // ==========================================================================
  async function fetchWithAuth(url, options = {}) {
    if (!state.token) {
      showLockScreen();
      throw new Error('Not authenticated');
    }

    const headers = new Headers(options.headers || {});
    headers.set('Authorization', `Bearer ${state.token}`);

    const res = await fetch(url, { ...options, headers });

    if (res.status === 401) {
      // Auto-logout on 401 Unauthorized
      state.token = null;
      localStorage.removeItem(STORAGE_KEY_TOKEN);
      showLockScreen();
      throw new Error('Unauthorized');
    }

    return res;
  }

  // ==========================================================================
  // Countdown Timer Engine (08:00 UTC Daily Reset)
  // ==========================================================================
  function startCutoffTimer(secondsRemaining) {
    if (secondsRemaining !== undefined && secondsRemaining !== null) {
      state.targetCutoffMs = Date.now() + Math.max(0, secondsRemaining) * 1000;
    }

    clearInterval(state.timerIntervalId);
    updateCutoffDisplay();

    state.timerIntervalId = setInterval(() => {
      updateCutoffDisplay();
    }, 1000);
  }

  function updateCutoffDisplay() {
    if (!state.targetCutoffMs || !el.countdownTimerText) return;

    const remainingMs = state.targetCutoffMs - Date.now();
    const remainingSec = Math.max(0, Math.floor(remainingMs / 1000));

    const hours = Math.floor(remainingSec / 3600);
    const minutes = Math.floor((remainingSec % 3600) / 60);
    const seconds = remainingSec % 60;

    const pad = (n) => String(n).padStart(2, '0');
    el.countdownTimerText.textContent = `${pad(hours)}ч ${pad(minutes)}м ${pad(seconds)}с`;

    // Urgency styles
    if (el.countdownPill) {
      el.countdownPill.classList.remove('urgent-warning', 'urgent-critical');
      if (remainingSec <= 1800) {
        // <= 30 min: Critical Red Pulse
        el.countdownPill.classList.add('urgent-critical');
      } else if (remainingSec <= 7200) {
        // <= 2 hours: Warning Amber
        el.countdownPill.classList.add('urgent-warning');
      }
    }
  }

  // ==========================================================================
  // Number & Currency Formatting
  // ==========================================================================
  function formatPoints(pts) {
    if (pts === null || pts === undefined || isNaN(pts)) return '0.00';
    return Number(pts).toLocaleString('en-US', {
      minimumFractionDigits: 1,
      maximumFractionDigits: 2
    });
  }

  // ==========================================================================
  // Hero Spotlight Card Rendering
  // ==========================================================================
  function renderHeroSpotlight(heroData) {
    if (!el.spotlightCard) return;

    el.spotlightStake.textContent = `${state.stake} Stake`;

    if (!state.heroNick) {
      // No hero set
      el.spotlightCard.className = 'hero-spotlight-card';
      el.spotlightRankBadge.className = 'large-rank-badge rank-unranked';
      el.spotlightRankBadge.textContent = '-';
      el.spotlightNick.textContent = 'No Hero Set';
      el.spotlightPoints.textContent = '0.0 pts';
      el.spotlightPrize.textContent = '-';
      el.spotlightPtsNext.textContent = 'Enter nickname';
      el.spotlightCushion.textContent = 'Enter nickname';
      if (el.spotlightDangerBanner) el.spotlightDangerBanner.classList.add('hidden');
      return;
    }

    if (!heroData || !heroData.found) {
      // Hero unranked (outside Top 50)
      el.spotlightCard.className = 'hero-spotlight-card';
      el.spotlightRankBadge.className = 'large-rank-badge rank-unranked';
      el.spotlightRankBadge.textContent = 'Out';
      el.spotlightNick.textContent = state.heroNick;
      
      const pts = heroData && heroData.points !== null ? heroData.points : 0;
      el.spotlightPoints.textContent = `${formatPoints(pts)} pts`;
      el.spotlightPrize.textContent = 'No Prize';

      const ptsToNext = heroData ? heroData.pts_to_next : null;
      if (ptsToNext !== null && ptsToNext !== undefined) {
        el.spotlightPtsNext.textContent = `+${ptsToNext.toFixed(1)} to #50`;
      } else {
        el.spotlightPtsNext.textContent = 'Need points for #50';
      }
      el.spotlightCushion.textContent = 'Outside Top 50';

      if (el.spotlightDangerBanner) el.spotlightDangerBanner.classList.add('hidden');
      return;
    }

    // Hero is ranked inside Top 50
    const rank = heroData.rank;
    el.spotlightNick.textContent = heroData.nickname || state.heroNick;
    el.spotlightPoints.textContent = `${formatPoints(heroData.points)} pts`;

    // Prize text
    let prizeStr = 'No Prize';
    if (heroData.prize && heroData.prize.text) {
      prizeStr = heroData.prize.text;
    } else if (heroData.prize_value && heroData.prize_value > 0) {
      prizeStr = `$${heroData.prize_value}`;
    }
    el.spotlightPrize.textContent = prizeStr;

    // Rank Badge Styling
    el.spotlightCard.className = 'hero-spotlight-card ranked';
    el.spotlightRankBadge.className = 'large-rank-badge';

    if (rank === 1) {
      el.spotlightRankBadge.classList.add('rank-1');
      el.spotlightRankBadge.textContent = '🥇';
    } else if (rank === 2) {
      el.spotlightRankBadge.classList.add('rank-2');
      el.spotlightRankBadge.textContent = '🥈';
    } else if (rank === 3) {
      el.spotlightRankBadge.classList.add('rank-3');
      el.spotlightRankBadge.textContent = '🥉';
    } else if (rank <= 10) {
      el.spotlightRankBadge.classList.add('rank-top10');
      el.spotlightRankBadge.textContent = `#${rank}`;
    } else {
      el.spotlightRankBadge.classList.add('rank-top10');
      el.spotlightRankBadge.textContent = `#${rank}`;
    }

    // Gap to Next Rank
    if (rank === 1) {
      el.spotlightPtsNext.textContent = '👑 Leader (#1)';
    } else if (heroData.pts_to_next !== null && heroData.pts_to_next !== undefined) {
      const tgt = heroData.target_rank ? `#${heroData.target_rank}` : 'next';
      let deltaStr = `+${heroData.pts_to_next.toFixed(1)} pts to ${tgt}`;
      if (heroData.prize_diff_to_next && heroData.prize_diff_to_next > 0) {
        deltaStr += ` (+$${heroData.prize_diff_to_next})`;
      }
      el.spotlightPtsNext.textContent = deltaStr;
    } else {
      el.spotlightPtsNext.textContent = '-';
    }

    // Defensive Cushion / Lead
    if (heroData.lead_over_prev !== null && heroData.lead_over_prev !== undefined) {
      const trailing = heroData.trailing_rank ? `#${heroData.trailing_rank}` : 'prev';
      el.spotlightCushion.textContent = `+${heroData.lead_over_prev.toFixed(1)} pts lead over ${trailing}`;
    } else if (rank === 50) {
      el.spotlightCushion.textContent = '⚠️ Bubble Rank #50';
    } else {
      el.spotlightCushion.textContent = 'Comfortable Cushion';
    }

    // Danger alerts
    if (el.spotlightDangerBanner) {
      if (heroData.cushion_danger) {
        el.spotlightCard.classList.add('danger');
        el.spotlightDangerBanner.classList.remove('hidden', 'warning-banner');
        const trail = heroData.trailing_rank ? `#${heroData.trailing_rank}` : 'chaser';
        el.dangerBannerText.textContent = `⚠️ Caution: Lead fragile (< 1 win ahead of ${trail})!`;
      } else if (rank === 50) {
        el.spotlightDangerBanner.classList.remove('hidden');
        el.spotlightDangerBanner.classList.add('warning-banner');
        el.dangerBannerText.textContent = '⚠️ Danger: Rank #50 is on the cut bubble!';
      } else {
        el.spotlightDangerBanner.classList.add('hidden');
      }
    }
  }

  // ==========================================================================
  // Leaderboard Table Rendering (Safe DOM / XSS Protected)
  // ==========================================================================
  function renderLeaderboardTable(players) {
    if (!el.leaderboardList) return;

    el.leaderboardList.innerHTML = '';

    if (!players || players.length === 0) {
      const emptyDiv = document.createElement('div');
      emptyDiv.className = 'hero-empty-notice';
      emptyDiv.textContent = 'No players registered on this stake yet.';
      el.leaderboardList.appendChild(emptyDiv);
      return;
    }

    const heroNickClean = state.heroNick.toLowerCase();
    let heroRowElement = null;

    players.forEach((player) => {
      const row = document.createElement('div');
      row.className = 'player-row';
      row.setAttribute('role', 'listitem');

      const isHero = player.is_hero || 
        (heroNickClean && player.nickname && player.nickname.toLowerCase() === heroNickClean);

      if (isHero) {
        row.classList.add('hero-row');
        heroRowElement = row;
      }

      // Left Column: Mini Badge + Nickname + Points
      const leftCol = document.createElement('div');
      leftCol.className = 'player-left';

      const badge = document.createElement('div');
      badge.className = 'rank-badge';

      const r = player.rank;
      if (r === 1) {
        badge.classList.add('rank-1');
        badge.textContent = '🥇';
      } else if (r === 2) {
        badge.classList.add('rank-2');
        badge.textContent = '🥈';
      } else if (r === 3) {
        badge.classList.add('rank-3');
        badge.textContent = '🥉';
      } else if (r <= 10) {
        badge.classList.add('rank-top10');
        badge.textContent = String(r);
      } else {
        badge.classList.add('rank-other');
        badge.textContent = String(r);
      }

      const nameWrapper = document.createElement('div');
      nameWrapper.className = 'player-name-wrapper';

      const nickEl = document.createElement('div');
      nickEl.className = 'player-nick';
      nickEl.textContent = player.nickname || `Player #${r}`;

      const pointsEl = document.createElement('div');
      pointsEl.className = 'player-points';
      pointsEl.textContent = `${formatPoints(player.points)} pts`;

      nameWrapper.appendChild(nickEl);
      nameWrapper.appendChild(pointsEl);

      leftCol.appendChild(badge);
      leftCol.appendChild(nameWrapper);

      // Right Column: Prize + Delta
      const rightCol = document.createElement('div');
      rightCol.className = 'player-right';

      const prizeEl = document.createElement('div');
      prizeEl.className = 'player-prize';

      let prizeText = '-';
      if (player.prize && player.prize.text) {
        prizeText = player.prize.text;
      } else if (player.prize_str) {
        prizeText = player.prize_str;
      } else if (player.prize && player.prize.value > 0) {
        prizeText = `$${player.prize.value}`;
      }
      prizeEl.textContent = prizeText;
      rightCol.appendChild(prizeEl);

      row.appendChild(leftCol);
      row.appendChild(rightCol);

      el.leaderboardList.appendChild(row);
    });

    // Auto-scroll to Hero row when present
    if (heroRowElement) {
      requestAnimationFrame(() => {
        heroRowElement.scrollIntoView({ behavior: 'smooth', block: 'center' });
      });
    }
  }

  // ==========================================================================
  // Data Fetching: Leaderboard & Telemetry
  // ==========================================================================
  async function fetchLeaderboardData(force = false) {
    if (state.isFetching) return;
    if (!state.token) {
      showLockScreen();
      return;
    }

    state.isFetching = true;
    setPulseState('syncing');
    if (el.btnRefresh) el.btnRefresh.classList.add('spinning');

    const params = new URLSearchParams({
      stake: state.stake,
      force: String(force)
    });
    if (state.heroNick) {
      params.set('hero', state.heroNick);
    }

    try {
      const response = await fetchWithAuth(`/api/leaderboard?${params.toString()}`);
      if (!response.ok) {
        throw new Error(`HTTP error ${response.status}`);
      }

      const data = await response.json();

      // Update cutoff countdown
      const cutoffSec = data.cutoff_seconds_remaining ?? data.cutoff_seconds;
      if (cutoffSec !== undefined && cutoffSec !== null) {
        startCutoffTimer(cutoffSec);
      }

      // Update table title
      if (el.tableTitle) {
        el.tableTitle.textContent = `${state.stake} Top 50 Rankings`;
      }

      // Update spotlight card
      renderHeroSpotlight(data.hero);

      // Render players list
      const players = data.players || data.leaderboard || [];
      renderLeaderboardTable(players);

      setPulseState('idle');
    } catch (err) {
      if (err.message !== 'Unauthorized' && err.message !== 'Not authenticated') {
        showToast('Sync error: GGPoker connection');
        setPulseState('error');
      }
    } finally {
      state.isFetching = false;
      if (el.btnRefresh) el.btnRefresh.classList.remove('spinning');
    }
  }

  // ==========================================================================
  // Fetch Stakes (Prize Pools)
  // ==========================================================================
  async function fetchStakesData() {
    if (!state.token) return;
    try {
      const response = await fetchWithAuth('/api/stakes');
      if (!response.ok) return;

      const data = await response.json();
      if (data.stakes && Array.isArray(data.stakes)) {
        const curStakeItem = data.stakes.find((s) => s.stake === state.stake);
        if (curStakeItem && curStakeItem.prize_pool && el.prizePoolBadge) {
          el.prizePoolBadge.textContent = `${curStakeItem.prize_pool} Pool`;
        }
      }
    } catch (_) {
      // Non-blocking background fetch
    }
  }

  // ==========================================================================
  // Auto-Refresh Controller
  // ==========================================================================
  function resetAutoRefresh() {
    clearInterval(state.refreshTimerId);
    if (state.refreshIntervalSec > 0) {
      state.refreshTimerId = setInterval(() => {
        if (!state.isFetching && state.token) {
          fetchLeaderboardData(false);
        }
      }, state.refreshIntervalSec * 1000);
    }
  }

  // ==========================================================================
  // Event Listeners Setup
  // ==========================================================================
  function setupEventListeners() {
    // 1. PIN Keypad button clicks
    el.pinButtons.forEach((btn) => {
      btn.addEventListener('click', (e) => {
        e.preventDefault();
        const key = btn.getAttribute('data-key');
        handleKeypadPress(key);
      });
    });

    // 2. Physical keyboard listener for PIN entry
    window.addEventListener('keydown', (e) => {
      if (el.pinOverlay && !el.pinOverlay.classList.contains('hidden')) {
        if (/^[0-9]$/.test(e.key)) {
          handleKeypadPress(e.key);
        } else if (e.key === 'Backspace') {
          if (state.pinBuffer.length > 0) {
            state.pinBuffer = state.pinBuffer.slice(0, -1);
            updatePinDots();
            if (el.pinError) el.pinError.textContent = '';
          }
        } else if (e.key === 'Enter') {
          handleKeypadPress('enter');
        } else if (e.key === 'Escape') {
          handleKeypadPress('clear');
        }
      }
    });

    // 3. Logout / Lock HUD button
    if (el.btnLogout) {
      el.btnLogout.addEventListener('click', (e) => {
        e.preventDefault();
        logout();
      });
    }

    // 4. Stake Chips selection
    if (el.stakeChipsScroll) {
      el.stakeChipsScroll.addEventListener('click', (e) => {
        const chip = e.target.closest('.stake-chip');
        if (!chip) return;

        const newStake = chip.getAttribute('data-stake');
        if (newStake && newStake !== state.stake) {
          state.stake = newStake;
          localStorage.setItem(STORAGE_KEY_STAKE, newStake);

          el.stakeChips.forEach((c) => c.classList.remove('active'));
          chip.classList.add('active');

          fetchLeaderboardData(false);
          fetchStakesData();
        }
      });
    }

    // 5. Hero Nickname Input & Persistence
    let heroInputDebounce = null;
    if (el.heroInput) {
      el.heroInput.value = state.heroNick;
      if (el.heroClear) {
        if (state.heroNick) el.heroClear.classList.add('visible');
      }

      el.heroInput.addEventListener('input', () => {
        const val = el.heroInput.value.trim();
        state.heroNick = val;
        localStorage.setItem(STORAGE_KEY_HERO, val);

        if (el.heroClear) {
          if (val) {
            el.heroClear.classList.add('visible');
          } else {
            el.heroClear.classList.remove('visible');
          }
        }

        clearTimeout(heroInputDebounce);
        heroInputDebounce = setTimeout(() => {
          fetchLeaderboardData(false);
        }, 350);
      });

      el.heroInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') {
          el.heroInput.blur();
          fetchLeaderboardData(false);
        }
      });
    }

    if (el.heroClear) {
      el.heroClear.addEventListener('click', () => {
        if (el.heroInput) el.heroInput.value = '';
        state.heroNick = '';
        localStorage.setItem(STORAGE_KEY_HERO, '');
        el.heroClear.classList.remove('visible');
        fetchLeaderboardData(false);
      });
    }

    // 6. Auto-Refresh Interval Selector
    if (el.refreshSelect) {
      el.refreshSelect.value = String(state.refreshIntervalSec);
      el.refreshSelect.addEventListener('change', () => {
        state.refreshIntervalSec = parseInt(el.refreshSelect.value, 10);
        localStorage.setItem(STORAGE_KEY_REFRESH, String(state.refreshIntervalSec));
        resetAutoRefresh();
        showToast(state.refreshIntervalSec > 0 ? `Auto-refresh: ${state.refreshIntervalSec}s` : 'Auto-refresh: Off');
      });
    }

    // 7. Manual Refresh Button
    if (el.btnRefresh) {
      el.btnRefresh.addEventListener('click', () => {
        fetchLeaderboardData(true);
        fetchStakesData();
      });
    }

    // 8. Pull-to-Refresh Gesture (Touch devices)
    window.addEventListener('touchstart', (e) => {
      if (window.scrollY <= 2 && e.touches.length === 1) {
        state.touchStartY = e.touches[0].clientY;
        state.isPulling = true;
      } else {
        state.isPulling = false;
      }
    }, { passive: true });

    window.addEventListener('touchmove', (e) => {
      if (!state.isPulling || e.touches.length !== 1) return;
      const currentY = e.touches[0].clientY;
      const deltaY = currentY - state.touchStartY;

      if (deltaY > 20 && window.scrollY <= 2) {
        if (el.pullIndicator) {
          el.pullIndicator.classList.add('visible');
          if (deltaY > 60) {
            el.pullIndicator.textContent = '↑ Release to refresh';
          } else {
            el.pullIndicator.textContent = '↓ Pull down to refresh';
          }
        }
      }
    }, { passive: true });

    window.addEventListener('touchend', (e) => {
      if (!state.isPulling) return;
      state.isPulling = false;

      if (el.pullIndicator && el.pullIndicator.classList.contains('visible')) {
        el.pullIndicator.classList.remove('visible');
        const touchEndY = e.changedTouches[0].clientY;
        if (touchEndY - state.touchStartY > 60) {
          fetchLeaderboardData(true);
          showToast('Refreshing leaderboard...');
        }
      }
    }, { passive: true });
  }

  // ==========================================================================
  // Progressive Web App: Service Worker Registration
  // ==========================================================================
  function registerServiceWorker() {
    if ('serviceWorker' in navigator) {
      window.addEventListener('load', () => {
        navigator.serviceWorker.register('/static/sw.js')
          .then((reg) => {
            console.log('[PWA] Service Worker registered:', reg.scope);
          })
          .catch((err) => {
            console.warn('[PWA] Service Worker registration failed:', err);
          });
      });
    }
  }

  // ==========================================================================
  // Application Bootstrap
  // ==========================================================================
  function init() {
    // 1. Restore active stake chip
    el.stakeChips.forEach((chip) => {
      if (chip.getAttribute('data-stake') === state.stake) {
        chip.classList.add('active');
      } else {
        chip.classList.remove('active');
      }
    });

    // 2. Setup listeners
    setupEventListeners();

    // 3. Register SW
    registerServiceWorker();

    // 4. Check Authentication Gate
    if (!state.token) {
      showLockScreen();
    } else {
      hideLockScreen();
      fetchLeaderboardData();
      fetchStakesData();
      resetAutoRefresh();
    }
  }

  // Launch on DOMContentLoaded
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
