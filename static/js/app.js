/**
 * GGPoker Spin & Gold Mobile Leaderboard HUD — Desktop Classic Edition
 * 1:1 visual & tactical parity with GG_Leaderboard_HUD.exe
 */

(() => {
  'use strict';

  // --- Constants & Storage Keys ---
  const STORAGE_KEY_TOKEN = 'gg_hud_token';
  const STORAGE_KEY_STAKE = 'gg_hud_stake';
  const STORAGE_KEY_HERO = 'gg_hud_hero';
  const STORAGE_KEY_REFRESH = 'gg_hud_refresh';
  const STORAGE_KEY_FONT = 'gg_hud_font_size';
  const STORAGE_KEY_FOCUS = 'gg_hud_focus_hero';
  const STORAGE_KEY_SOUND = 'gg_hud_sound';

  const DEFAULT_STAKE = '$0.25';
  const DEFAULT_REFRESH = '10';
  const DEFAULT_FONT_SIZE = 10.5;

  // --- Application State ---
  const state = {
    token: localStorage.getItem(STORAGE_KEY_TOKEN) || null,
    stake: localStorage.getItem(STORAGE_KEY_STAKE) || DEFAULT_STAKE,
    heroNick: (localStorage.getItem(STORAGE_KEY_HERO) || '').trim(),
    refreshIntervalSec: parseInt(localStorage.getItem(STORAGE_KEY_REFRESH) || DEFAULT_REFRESH, 10),
    fontSize: parseFloat(localStorage.getItem(STORAGE_KEY_FONT) || String(DEFAULT_FONT_SIZE)),
    focusHero: localStorage.getItem(STORAGE_KEY_FOCUS) !== 'false',
    soundAlert: localStorage.getItem(STORAGE_KEY_SOUND) !== 'false',

    // Telemetry & Timers
    targetCutoffMs: null,
    nextRefreshMs: 0,
    timerIntervalId: null,
    isFetching: false,

    // Rankings & Delta tracking (matching desktop HUD)
    rankings: [],
    prevPoints: {},
    lastHeroRank: null,

    // PIN pad buffer
    pinBuffer: '',

    // Touch pull-to-refresh
    touchStartY: 0,
    isPulling: false
  };

  if (isNaN(state.refreshIntervalSec)) state.refreshIntervalSec = 10;
  if (isNaN(state.fontSize)) state.fontSize = DEFAULT_FONT_SIZE;

  // --- DOM Elements ---
  const el = {
    // Top bar
    pulseDot: document.getElementById('pulse-dot'),
    countdownPill: document.getElementById('countdown-pill'),
    countdownTimerText: document.getElementById('countdown-timer-text'),
    topTimerLbl: document.getElementById('top-timer-lbl'),
    btnRefresh: document.getElementById('btn-refresh'),
    btnLogout: document.getElementById('btn-logout'),

    // Control bar
    stakeSelect: document.getElementById('stake-select'),
    stakeChipsScroll: document.getElementById('stake-chips-scroll'),
    stakeChips: document.querySelectorAll('.stake-chip'),
    refreshSelect: document.getElementById('refresh-interval'),
    btnFontMinus: document.getElementById('btn-font-minus'),
    fontSizeInput: document.getElementById('font-size-input'),
    btnFontPlus: document.getElementById('btn-font-plus'),

    // Hero bar
    heroInput: document.getElementById('hero-input'),
    heroClear: document.getElementById('hero-clear'),
    btnHeroOk: document.getElementById('btn-hero-ok'),
    chkFocusHero: document.getElementById('chk-focus-hero'),
    chkSound: document.getElementById('chk-sound'),
    pullIndicator: document.getElementById('pull-indicator'),

    // Desktop HUD Boxes
    heroStatusLbl: document.getElementById('hero-status-lbl'),
    advisorLbl: document.getElementById('advisor-lbl'),

    // Legacy Spotlight Card (kept synced for test compatibility)
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

    // Table & Status bar
    tableTitle: document.getElementById('table-title'),
    prizePoolBadge: document.getElementById('prize-pool-badge'),
    leaderboardList: document.getElementById('leaderboard-list'),
    statusLbl: document.getElementById('status-lbl'),
    nextUpdateLbl: document.getElementById('next-update-lbl'),

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
  // Sound Alert Helper (Web Audio API beep when Hero rank changes)
  // ==========================================================================
  function playRankChangeBeep() {
    if (!state.soundAlert) return;
    try {
      const AudioCtx = window.AudioContext || window.webkitAudioContext;
      if (!AudioCtx) return;
      const ctx = new AudioCtx();
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.type = 'sine';
      osc.frequency.setValueAtTime(880, ctx.currentTime);
      gain.gain.setValueAtTime(0.08, ctx.currentTime);
      gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.18);
      osc.connect(gain);
      gain.connect(ctx.destination);
      osc.start();
      osc.stop(ctx.currentTime + 0.18);
    } catch (_) {
      // Ignore audio autoplay restrictions
    }
  }

  // ==========================================================================
  // Font Scaling (matching apply_font_scale in leaderboard_hud.py)
  // ==========================================================================
  function applyFontScale(sizeVal) {
    const clamped = Math.max(7.0, Math.min(18.0, Math.round(Number(sizeVal) * 100) / 100));
    state.fontSize = clamped;
    localStorage.setItem(STORAGE_KEY_FONT, String(clamped));

    if (el.fontSizeInput) {
      el.fontSizeInput.value = clamped.toFixed(2);
    }

    const pxSize = Math.round(clamped * 1.24);
    const rowH = Math.max(20, Math.round(clamped * 2.48));

    document.documentElement.style.setProperty('--table-font-size', `${pxSize}px`);
    document.documentElement.style.setProperty('--table-row-height', `${rowH}px`);
  }

  // ==========================================================================
  // Toast & UI Feedback Helpers
  // ==========================================================================
  let toastTimeout = null;
  function showToast(message, duration = 2500) {
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
      if (!dot) return;
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
      void el.pinModalCard.offsetWidth;
      el.pinModalCard.classList.add('shake');
    }
    state.pinBuffer = '';
    updatePinDots();
  }

  async function submitPin(pinCode) {
    if (!pinCode || pinCode.length < 1) {
      triggerPinError('Введите ПИН-код');
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
        triggerPinError(data.detail || 'Неверный ПИН-код');
        setPulseState('error');
        return;
      }

      const data = await response.json();
      if (data.token) {
        state.token = data.token;
        localStorage.setItem(STORAGE_KEY_TOKEN, state.token);
        hideLockScreen();
        showToast('Доступ открыт');
        setPulseState('idle');
        fetchLeaderboardData(true);
      } else {
        triggerPinError('Ошибка авторизации');
      }
    } catch (err) {
      triggerPinError('Ошибка соединения с сервером');
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
          submitPin(state.pinBuffer);
        }
      }
    }
  }

  function logout() {
    state.token = null;
    localStorage.removeItem(STORAGE_KEY_TOKEN);
    showToast('HUD заблокирован');
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
      state.token = null;
      localStorage.removeItem(STORAGE_KEY_TOKEN);
      showLockScreen();
      throw new Error('Unauthorized');
    }

    return res;
  }

  // ==========================================================================
  // Master 1-Second Timer Loop (Day Cutoff + Auto-Refresh Countdown)
  // ==========================================================================
  function startCutoffTimer(secondsRemaining) {
    if (secondsRemaining !== undefined && secondsRemaining !== null) {
      state.targetCutoffMs = Date.now() + Math.max(0, secondsRemaining) * 1000;
    }
    updateCutoffDisplay();
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

    if (el.countdownPill) {
      el.countdownPill.classList.remove('urgent-warning', 'urgent-critical');
      if (remainingSec <= 1800) {
        el.countdownPill.classList.add('urgent-critical');
      } else if (remainingSec <= 7200) {
        el.countdownPill.classList.add('urgent-warning');
      }
    }
  }

  function scheduleNextRefresh() {
    if (state.refreshIntervalSec > 0) {
      state.nextRefreshMs = Date.now() + state.refreshIntervalSec * 1000;
      if (el.topTimerLbl) {
        el.topTimerLbl.textContent = `⏱ ${state.refreshIntervalSec}с`;
        el.topTimerLbl.style.color = '#ffffff';
      }
      if (el.nextUpdateLbl) {
        el.nextUpdateLbl.textContent = `${state.refreshIntervalSec}с`;
        el.nextUpdateLbl.style.color = '#ffffff';
      }
    } else {
      state.nextRefreshMs = 0;
      if (el.topTimerLbl) {
        el.topTimerLbl.textContent = '⏸ Вручную';
        el.topTimerLbl.style.color = '#888888';
      }
      if (el.nextUpdateLbl) {
        el.nextUpdateLbl.textContent = 'Выкл';
        el.nextUpdateLbl.style.color = '#888888';
      }
    }
  }

  function startMasterTimerLoop() {
    clearInterval(state.timerIntervalId);
    state.timerIntervalId = setInterval(() => {
      // 1. Update day cutoff countdown
      updateCutoffDisplay();

      // 2. Update auto-refresh countdown (matching _timer_tick in leaderboard_hud.py)
      if (!state.token) return;

      if (state.refreshIntervalSec > 0 && state.nextRefreshMs > 0) {
        if (state.isFetching) return;
        const remaining = Math.ceil((state.nextRefreshMs - Date.now()) / 1000);
        if (remaining > 0) {
          if (el.topTimerLbl) {
            el.topTimerLbl.textContent = `⏱ ${remaining}с`;
            el.topTimerLbl.style.color = '#ffffff';
          }
          if (el.nextUpdateLbl) {
            el.nextUpdateLbl.textContent = `${remaining}с`;
            el.nextUpdateLbl.style.color = '#ffffff';
          }
        } else {
          if (el.topTimerLbl) {
            el.topTimerLbl.textContent = '⏳ ...';
            el.topTimerLbl.style.color = '#e5c07b';
          }
          if (el.nextUpdateLbl) {
            el.nextUpdateLbl.textContent = 'обновление...';
            el.nextUpdateLbl.style.color = '#e5c07b';
          }
          fetchLeaderboardData(true);
        }
      } else if (state.refreshIntervalSec <= 0) {
        if (el.topTimerLbl) {
          el.topTimerLbl.textContent = '⏸ Вручную';
          el.topTimerLbl.style.color = '#888888';
        }
        if (el.nextUpdateLbl) {
          el.nextUpdateLbl.textContent = 'Выкл';
          el.nextUpdateLbl.style.color = '#888888';
        }
      }
    }, 1000);
  }

  // ==========================================================================
  // Number & Currency Formatting
  // ==========================================================================
  function formatPoints(pts) {
    if (pts === null || pts === undefined || isNaN(pts)) return '0.00';
    return Number(pts).toLocaleString('en-US', {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2
    });
  }

  function getPrizeDollarValue(player) {
    if (!player) return 0;
    if (player.prize && typeof player.prize.value === 'number') {
      return player.prize.value;
    }
    if (typeof player.prize_value === 'number') {
      return player.prize_value;
    }
    return 0;
  }

  // ==========================================================================
  // Desktop Box 1 & Box 2: Hero Banner & Smart Advisor
  // ==========================================================================
  function renderDesktopBoxes(players, heroRank, heroPoints, heroPrize) {
    // --- Box 1: Hero Status Banner (_render_hero_banner) ---
    if (el.heroStatusLbl) {
      if (!state.heroNick) {
        el.heroStatusLbl.textContent = 'Введи свой игровой ник выше, чтобы активировать персонального советника гонки.';
        el.heroStatusLbl.style.color = '#abb2bf';
      } else if (heroRank === null) {
        el.heroStatusLbl.textContent = `🔍 Ник '${state.heroNick}' не найден в Топ-${players.length}. Сыграй ещё спины, чтобы войти в топ!`;
        el.heroStatusLbl.style.color = '#e5c07b';
      } else {
        let targetInfo = '';
        let threatInfo = '';

        if (heroRank > 1 && players[heroRank - 2]) {
          const abovePlayer = players[heroRank - 2];
          const abovePts = Number(abovePlayer.points || 0);
          const ptsNeeded = Math.max(0, abovePts - heroPoints);
          const abovePrize = getPrizeDollarValue(abovePlayer);
          const prizeGain = abovePrize - heroPrize;
          const spinsEst = Math.max(1, Math.floor(ptsNeeded / 2.5));
          const gainText = prizeGain > 0 ? `(+$$${prizeGain})`.replace('$$', '$') : '';
          targetInfo = `🎯 До #${heroRank - 1}: +${ptsNeeded.toFixed(1)} pts (~${spinsEst} побед) ${gainText}`.trim();
        }

        if (heroRank < players.length && players[heroRank]) {
          const belowPlayer = players[heroRank];
          const belowPts = Number(belowPlayer.points || 0);
          const lead = Math.max(0, heroPoints - belowPts);
          threatInfo = `🛡️ Отрыв от #${heroRank + 1}: +${lead.toFixed(1)} pts`;
          if (lead < 15) {
            threatInfo += ' ⚠️ ДЫШАТ В СПИНУ!';
          }
        }

        const sep = targetInfo && threatInfo ? '   |   ' : '';
        el.heroStatusLbl.textContent = `👤 HERO: #${heroRank} | Очки: ${formatPoints(heroPoints)} | Приз: $${heroPrize}\n${targetInfo}${sep}${threatInfo}`;
        el.heroStatusLbl.style.color = heroRank <= 10 ? '#61afef' : '#98c379';
      }
    }

    // --- Box 2: Smart Advisor (_render_advisor) ---
    if (el.advisorLbl && players && players.length > 0) {
      const top1 = players[0];
      const top1Pts = Number(top1.points || 0);
      const top2Pts = players.length > 1 ? Number(players[1].points || 0) : 0.0;
      const top3Pts = players.length > 2 ? Number(players[2].points || 0) : 0.0;

      const lines = [];

      if (heroRank !== null) {
        if (heroRank === 1) {
          const lead = heroPoints - top2Pts;
          lines.push(`👑 ТЫ ТОП-1! Твой отрыв от 2-го места: +${lead.toFixed(1)} pts. Удерживай темп!`);
        } else {
          const gapTo1 = top1Pts - heroPoints;
          const gapTo3 = top3Pts - heroPoints;

          if (gapTo1 > 500) {
            lines.push(`❌ Топ-1 (${top1.nickname}) недосягаем (+${gapTo1.toFixed(0)} pts ~ ${Math.floor(gapTo1 / 2.5)} побед). НЕ СЛИВАЙ СИЛЫ!`);
          } else if (gapTo1 > 150) {
            lines.push(`⚠️ До Топ-1 тяжело (+${gapTo1.toFixed(0)} pts). Рекомендуется фокус на Топ-2/Топ-3.`);
          } else {
            lines.push(`🔥 ДО ТОП-1 ВСЕГО +${gapTo1.toFixed(0)} pts (~${Math.floor(gapTo1 / 2.5)} побед)! ИМЕЕТ СМЫСЛ БОРОТЬСЯ!`);
          }

          if (heroRank > 3 && players.length > 2) {
            const top3Prize = getPrizeDollarValue(players[2]);
            if (gapTo3 <= 60) {
              lines.push(`💎 Топ-3 в шаговой доступности (+${gapTo3.toFixed(1)} pts ~ ${Math.max(1, Math.floor(gapTo3 / 2.5))} побед, приз $${top3Prize})! ДОЖИМАЙ!`);
            } else if (gapTo3 <= 150) {
              lines.push(`🎯 До Топ-3 дистанция +${gapTo3.toFixed(1)} pts (~${Math.floor(gapTo3 / 2.5)} побед). Реально при 1.5-2 часах катки.`);
            }
          }

          if (heroRank < players.length && players[heroRank]) {
            const belowPts = Number(players[heroRank].points || 0);
            const lead = heroPoints - belowPts;
            if (lead < 20) {
              lines.push(`🚨 ОПАСНОСТЬ: Твоё место #${heroRank} под угрозой! Игрок снизу отстает всего на ${lead.toFixed(1)} pts!`);
            }
          }
        }
      } else {
        const gap12 = top1Pts - top2Pts;
        const gap23 = top2Pts - top3Pts;
        lines.push(`📊 Лидер: ${top1.nickname} (${top1Pts.toFixed(0)} pts). Отрыв от 2 места: +${gap12.toFixed(0)} pts.`);
        if (gap23 < 50) {
          lines.push(`⚔️ Ожесточенная битва за Серебро (Топ-2 vs Топ-3): разрыв всего ${gap23.toFixed(1)} pts!`);
        } else {
          lines.push(`🥈 Разрыв Топ-2 и Топ-3: ${gap23.toFixed(1)} pts.`);
        }

        if (players.length >= 10) {
          const p10Pts = Number(players[9].points || 0);
          const p11Pts = players.length > 10 ? Number(players[10].points || 0) : 0;
          lines.push(`🚪 Граница Топ-10: #10 (${p10Pts.toFixed(0)} pts) vs #11 (${p11Pts.toFixed(0)} pts, разрыв ${(p10Pts - p11Pts).toFixed(1)} pts).`);
        }
      }

      el.advisorLbl.textContent = lines.join('\n');
    }
  }

  // ==========================================================================
  // Legacy Spotlight Sync (Preserves DOM bindings for automated test suite)
  // ==========================================================================
  function renderHeroSpotlight(heroData) {
    if (!el.spotlightCard) return;
    if (el.spotlightStake) el.spotlightStake.textContent = `${state.stake} Stake`;

    if (!state.heroNick || !heroData || !heroData.found) {
      el.spotlightNick.textContent = state.heroNick || 'No Hero Set';
      el.spotlightPoints.textContent = '0.0 pts';
      el.spotlightPrize.textContent = '-';
      el.spotlightPtsNext.textContent = '-';
      el.spotlightCushion.textContent = '-';
      el.dangerBannerText.textContent = '';
      return;
    }

    el.spotlightNick.textContent = heroData.nickname || state.heroNick;
    el.spotlightPoints.textContent = `${formatPoints(heroData.points)} pts`;
    el.spotlightPrize.textContent = heroData.prize_value ? `$${heroData.prize_value}` : '-';
    el.spotlightPtsNext.textContent = heroData.pts_to_next !== null ? `+${heroData.pts_to_next}` : '-';
    el.spotlightCushion.textContent = heroData.lead_over_prev !== null ? `+${heroData.lead_over_prev}` : '-';
    el.dangerBannerText.textContent = heroData.cushion_danger ? 'Danger' : '';
  }

  // ==========================================================================
  // Leaderboard Table Rendering (6-Column Desktop Layout, Safe textContent)
  // ==========================================================================
  function renderLeaderboardTable(players) {
    if (!el.leaderboardList) return;

    el.leaderboardList.innerHTML = '';

    if (!players || players.length === 0) {
      const emptyDiv = document.createElement('div');
      emptyDiv.className = 'hero-empty-notice';
      emptyDiv.textContent = 'Нет данных по игрокам на выбранном лимите.';
      el.leaderboardList.appendChild(emptyDiv);
      return;
    }

    const heroSearch = state.heroNick ? state.heroNick.toLowerCase() : null;
    let heroRowElement = null;
    let heroRank = null;
    let heroPoints = null;
    let heroPrize = 0;

    players.forEach((player, idx) => {
      const row = document.createElement('div');
      row.className = 'player-row';
      row.setAttribute('role', 'listitem');

      const r = player.rank || (idx + 1);
      const nick = player.nickname || `Player #${r}`;
      const country = player.country || '';
      const ptVal = Number(player.points || 0);
      const prizeVal = getPrizeDollarValue(player);

      // 1. Dynamic gain delta since previous fetch
      const prevPt = state.prevPoints[nick];
      let gainStr = '';
      if (prevPt !== undefined && prevPt !== null) {
        const delta = ptVal - prevPt;
        if (delta > 0) {
          gainStr = `+${Math.round(delta)}`;
        }
      }
      state.prevPoints[nick] = ptVal;

      // 2. Prize string ($18, $15, etc. — matching desktop HUD)
      const prizeStr = prizeVal > 0 ? `$${prizeVal}` : '-';

      // 3. Gap to previous player (ЛИДЕР for #1, +diff for #2+)
      let gapStr = 'ЛИДЕР';
      if (idx > 0) {
        const prevPlayerPts = Number(players[idx - 1].points || 0);
        const diff = Math.max(0, prevPlayerPts - ptVal);
        gapStr = `+${diff.toFixed(1)}`;
      }

      // 4. Check if Hero (exact or substring match, matching leaderboard_hud.py)
      const isHero = Boolean(
        player.is_hero ||
        (heroSearch && nick.toLowerCase().includes(heroSearch))
      );

      if (isHero) {
        heroRank = r;
        heroPoints = ptVal;
        heroPrize = prizeVal;
        row.classList.add('hero-row');
        heroRowElement = row;
      } else if (r === 1) {
        row.classList.add('row-top1');
      } else if (r === 2) {
        row.classList.add('row-top2');
      } else if (r === 3) {
        row.classList.add('row-top3');
      } else if (prizeVal > 0) {
        row.classList.add('row-paid');
      } else {
        row.classList.add('row-unpaid');
      }

      // Column 1: #
      const rankEl = document.createElement('div');
      rankEl.className = 'cell-rank';
      rankEl.textContent = String(r);

      // Column 2: Игрок (with [country] code)
      const nickEl = document.createElement('div');
      nickEl.className = 'player-nick';
      nickEl.textContent = country ? `${nick} [${country}]` : nick;

      // Column 3: Очки
      const pointsEl = document.createElement('div');
      pointsEl.className = 'player-points';
      pointsEl.textContent = formatPoints(ptVal);

      // Column 4: Δ
      const gainEl = document.createElement('div');
      gainEl.className = 'cell-gain';
      gainEl.textContent = gainStr;

      // Column 5: Приз ($)
      const prizeEl = document.createElement('div');
      prizeEl.className = 'player-prize';
      prizeEl.textContent = prizeStr;

      // Column 6: Разрыв
      const gapEl = document.createElement('div');
      gapEl.className = 'cell-gap';
      gapEl.textContent = gapStr;

      row.appendChild(rankEl);
      row.appendChild(nickEl);
      row.appendChild(pointsEl);
      row.appendChild(gainEl);
      row.appendChild(prizeEl);
      row.appendChild(gapEl);

      el.leaderboardList.appendChild(row);
    });

    // Sound alert if Hero rank changed
    if (heroRank !== null && state.lastHeroRank !== null && heroRank !== state.lastHeroRank) {
      playRankChangeBeep();
    }
    state.lastHeroRank = heroRank;

    // Auto-scroll to Hero row if Focus on Hero is checked
    if (heroRowElement && state.focusHero) {
      requestAnimationFrame(() => {
        heroRowElement.scrollIntoView({ behavior: 'smooth', block: 'center' });
      });
    }

    // Update Hero Banner & Smart Advisor Box
    renderDesktopBoxes(players, heroRank, heroPoints, heroPrize);
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

    if (el.btnRefresh) {
      el.btnRefresh.textContent = '⏳ Загрузка...';
      el.btnRefresh.disabled = true;
    }
    if (el.topTimerLbl) {
      el.topTimerLbl.textContent = '⏳ ...';
      el.topTimerLbl.style.color = '#e5c07b';
    }
    if (el.statusLbl) {
      el.statusLbl.textContent = 'Получение свежих данных GG Leaderboard API...';
      el.statusLbl.style.color = '#e5c07b';
    }

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
        throw new Error(`HTTP ${response.status}`);
      }

      const data = await response.json();

      // Update cutoff countdown
      const cutoffSec = data.cutoff_seconds_remaining ?? data.cutoff_seconds;
      if (cutoffSec !== undefined && cutoffSec !== null) {
        startCutoffTimer(cutoffSec);
      }

      if (el.tableTitle) {
        el.tableTitle.textContent = `${state.stake} Top 50 Rankings`;
      }

      renderHeroSpotlight(data.hero);

      const players = data.players || data.leaderboard || [];
      state.rankings = players;
      renderLeaderboardTable(players);

      const nowStr = new Date().toLocaleTimeString('ru-RU', { hour12: false });
      if (el.statusLbl) {
        el.statusLbl.textContent = `Обновлено в ${nowStr} (${players.length} игроков загружено)`;
        el.statusLbl.style.color = '#98c379';
      }

      scheduleNextRefresh();
      setPulseState('idle');
    } catch (err) {
      if (err.message !== 'Unauthorized' && err.message !== 'Not authenticated') {
        if (el.statusLbl) {
          el.statusLbl.textContent = `Ошибка: ${err.message}`;
          el.statusLbl.style.color = '#e06c75';
        }
        state.nextRefreshMs = Date.now() + 15000;
        setPulseState('error');
      }
    } finally {
      state.isFetching = false;
      if (el.btnRefresh) {
        el.btnRefresh.textContent = '🔄 Обновить';
        el.btnRefresh.disabled = false;
      }
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
      // Non-blocking
    }
  }

  function syncStakeSelectors(newStake) {
    state.stake = newStake;
    localStorage.setItem(STORAGE_KEY_STAKE, newStake);
    if (el.stakeSelect) {
      el.stakeSelect.value = newStake;
    }
    el.stakeChips.forEach((c) => {
      if (c.getAttribute('data-stake') === newStake) {
        c.classList.add('active');
      } else {
        c.classList.remove('active');
      }
    });
  }

  function applyHeroChange() {
    if (!el.heroInput) return;
    const val = el.heroInput.value.trim();
    state.heroNick = val;
    localStorage.setItem(STORAGE_KEY_HERO, val);
    if (el.heroClear) {
      if (val) el.heroClear.classList.add('visible');
      else el.heroClear.classList.remove('visible');
    }
    if (state.rankings && state.rankings.length > 0) {
      renderLeaderboardTable(state.rankings);
    } else {
      fetchLeaderboardData(false);
    }
  }

  // ==========================================================================
  // Event Listeners Setup
  // ==========================================================================
  function setupEventListeners() {
    // 1. PIN Keypad
    el.pinButtons.forEach((btn) => {
      btn.addEventListener('click', (e) => {
        e.preventDefault();
        const key = btn.getAttribute('data-key');
        handleKeypadPress(key);
      });
    });

    // 2. Physical keyboard for PIN
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

    // 4. Stake Dropdown & Chips
    if (el.stakeSelect) {
      el.stakeSelect.value = state.stake;
      el.stakeSelect.addEventListener('change', () => {
        const newStake = el.stakeSelect.value;
        if (newStake && newStake !== state.stake) {
          state.prevPoints = {};
          syncStakeSelectors(newStake);
          fetchLeaderboardData(false);
          fetchStakesData();
        }
      });
    }

    if (el.stakeChipsScroll) {
      el.stakeChipsScroll.addEventListener('click', (e) => {
        const chip = e.target.closest('.stake-chip');
        if (!chip) return;
        const newStake = chip.getAttribute('data-stake');
        if (newStake && newStake !== state.stake) {
          state.prevPoints = {};
          syncStakeSelectors(newStake);
          fetchLeaderboardData(false);
          fetchStakesData();
        }
      });
    }

    // 5. Font Zoom Controls (- 10.50 +)
    if (el.btnFontMinus) {
      el.btnFontMinus.addEventListener('click', () => {
        applyFontScale(state.fontSize - 0.25);
      });
    }
    if (el.btnFontPlus) {
      el.btnFontPlus.addEventListener('click', () => {
        applyFontScale(state.fontSize + 0.25);
      });
    }
    if (el.fontSizeInput) {
      el.fontSizeInput.addEventListener('change', () => {
        const val = parseFloat(el.fontSizeInput.value.replace(',', '.'));
        if (!isNaN(val)) {
          applyFontScale(val);
        } else {
          el.fontSizeInput.value = state.fontSize.toFixed(2);
        }
      });
    }

    // 6. Hero Nickname Input, OK Button, Checkboxes
    if (el.heroInput) {
      el.heroInput.value = state.heroNick;
      if (el.heroClear && state.heroNick) {
        el.heroClear.classList.add('visible');
      }

      el.heroInput.addEventListener('input', () => {
        if (el.heroClear) {
          if (el.heroInput.value.trim()) el.heroClear.classList.add('visible');
          else el.heroClear.classList.remove('visible');
        }
      });

      el.heroInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') {
          el.heroInput.blur();
          applyHeroChange();
        }
      });
    }

    if (el.btnHeroOk) {
      el.btnHeroOk.addEventListener('click', () => {
        applyHeroChange();
      });
    }

    if (el.heroClear) {
      el.heroClear.addEventListener('click', () => {
        if (el.heroInput) el.heroInput.value = '';
        applyHeroChange();
      });
    }

    if (el.chkFocusHero) {
      el.chkFocusHero.checked = state.focusHero;
      el.chkFocusHero.addEventListener('change', () => {
        state.focusHero = el.chkFocusHero.checked;
        localStorage.setItem(STORAGE_KEY_FOCUS, String(state.focusHero));
        if (state.focusHero && state.rankings.length > 0) {
          renderLeaderboardTable(state.rankings);
        }
      });
    }

    if (el.chkSound) {
      el.chkSound.checked = state.soundAlert;
      el.chkSound.addEventListener('change', () => {
        state.soundAlert = el.chkSound.checked;
        localStorage.setItem(STORAGE_KEY_SOUND, String(state.soundAlert));
      });
    }

    // 7. Auto-Refresh Interval Selector
    if (el.refreshSelect) {
      const validValues = Array.from(el.refreshSelect.options).map((o) => o.value);
      if (!validValues.includes(String(state.refreshIntervalSec))) {
        state.refreshIntervalSec = 10;
      }
      el.refreshSelect.value = String(state.refreshIntervalSec);
      el.refreshSelect.addEventListener('change', () => {
        state.refreshIntervalSec = parseInt(el.refreshSelect.value, 10);
        localStorage.setItem(STORAGE_KEY_REFRESH, String(state.refreshIntervalSec));
        scheduleNextRefresh();
      });
    }

    // 8. Manual Refresh Button
    if (el.btnRefresh) {
      el.btnRefresh.addEventListener('click', () => {
        fetchLeaderboardData(true);
        fetchStakesData();
      });
    }

    // 9. Pull-to-Refresh Gesture
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
          el.pullIndicator.textContent = deltaY > 60 ? '↑ Отпустите для обновления' : '↓ Потяните вниз для обновления';
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
    syncStakeSelectors(state.stake);
    applyFontScale(state.fontSize);
    setupEventListeners();
    registerServiceWorker();
    startMasterTimerLoop();

    if (!state.token) {
      showLockScreen();
    } else {
      hideLockScreen();
      fetchLeaderboardData(false);
      fetchStakesData();
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
