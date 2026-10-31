// SHL live! shell for the Samsung TV (docs/TV_APP.md). It shows the HDMI picture (the
// Telia box) behind its transparent page, registers the remote's keys and loads the
// overlay from the SHL Arena service on the LAN: in an iframe (/tv/), or, in the fallback
// mode, by importing /tv/tv.js into this page. The overlay never calls Tizen itself; it
// asks the shell over postMessage ({to: "shell"}) and gets keys back ({to: "overlay"}).
// On a computer the page runs as a preview: no HDMI, the keyboard is the remote.
(function () {
  'use strict';
  const VERSION = '1.0.0';
  const W = 1920, H = 1080;
  const STORE = 'shllive.settings';
  const api = window.tizen;
  const realTV = !!(api && api.tvwindow && api.systeminfo);
  const $ = (id) => document.getElementById(id);

  // remote key codes (after registerKey) and the computer's stand-ins
  const KEYS = {
    13: 'ok', 37: 'left', 38: 'up', 39: 'right', 40: 'down', 10009: 'back', 27: 'back', 8: 'back',
    403: 'red', 404: 'green', 405: 'yellow', 406: 'blue', 10252: 'playpause', 415: 'play', 19: 'pause',
    82: 'red', 71: 'green', 89: 'yellow', 66: 'blue', 32: 'playpause',
  };
  for (let d = 0; d <= 9; d++) { KEYS[48 + d] = String(d); KEYS[96 + d] = String(d); }
  // Every key the TV lets an app have is registered, so the test page can show which of
  // them the remote really has (it has no digits or colour keys of its own, 2026-10-31).
  const KEEP_FOR_TV = /^(Volume|Power|Exit|Source|Home|Menu)/;
  const supported = {}; // code -> name, from tvinputdevice
  const IME_DONE = 65376, IME_CANCEL = 65385;

  let settings = loadSettings();
  let lines = [];
  let base = null;           // http://host:port of the service
  let overlayReady = false;
  let retryTimer = null;
  let readyTimer = null;
  // The graphics say "ready" when they start and every 10 s after (a heartbeat). Silent for
  // this long (an error page while the service was down, a hang): load them again.
  const SILENT_MS = 30000;
  let lastReady = 0;
  let reloading = false;
  const iframe = $('overlay');

  // ---- small helpers --------------------------------------------------------------------

  function loadSettings() {
    let saved = {};
    try { saved = JSON.parse(localStorage.getItem(STORE) || '{}'); } catch (err) { saved = {}; }
    return { server: saved.server || '', hdmi: Number(saved.hdmi) || 1, mode: saved.mode === 'direct' ? 'direct' : 'iframe' };
  }
  function saveSettings() {
    try { localStorage.setItem(STORE, JSON.stringify(settings)); } catch (err) { log('Kunde inte spara inställningar: ' + err); }
  }
  function log(message) {
    lines.push(message);
    if (lines.length > 10) lines.shift();
    $('log').textContent = lines.join('\n');
    console.log('[shell] ' + message);
  }
  function status(text, hint) {
    $('status').classList.remove('hidden');
    $('status-text').textContent = text;
    $('status-hint').textContent = hint || '';
  }
  function fit() {
    const scale = Math.min(window.innerWidth / W, window.innerHeight / H);
    $('stage').style.transform = 'scale(' + scale + ')';
  }
  function serverBase(server) {
    const s = server.trim().replace(/\/+$/, '');
    return /^https?:\/\//.test(s) ? s : 'http://' + s;
  }

  // ---- HDMI (from the demo) ----------------------------------------------------------------

  const tv = { sources: [], index: -1, busy: false, op: 0, timer: null, shown: false, rect: null };
  let source = { hdmi: settings.hdmi, ok: false, error: realTV ? 'söker' : 'ingen HDMI på dator' };

  function setSource(next) {
    source = Object.assign({ hdmi: settings.hdmi }, next);
    toOverlay({ t: 'source', hdmi: source.hdmi, ok: source.ok, error: source.error || null });
  }
  function begin() {
    tv.busy = true;
    const token = ++tv.op;
    clearTimeout(tv.timer);
    tv.timer = setTimeout(function () {
      if (token !== tv.op) return;
      tv.op++;
      tv.busy = false;
      log('HDMI: inget svar inom 10 s');
      setSource({ ok: false, error: 'inget svar inom 10 s' });
    }, 10000);
    return token;
  }
  function done(token) {
    if (token !== tv.op) return false;
    clearTimeout(tv.timer);
    tv.busy = false;
    return true;
  }
  function fail(token, where, err) {
    if (!done(token)) return;
    const text = where + ': ' + (err.name || 'Error') + ' – ' + (err.message || String(err));
    log(text);
    setSource({ ok: false, error: text });
  }
  function percent(rect) {
    if (!rect) return ['0%', '0%', '100%', '100%'];
    return [rect[0] / W, rect[1] / H, rect[2] / W, rect[3] / H].map(function (v) { return (v * 100).toFixed(3) + '%'; });
  }
  function showWindow(token) {
    if (token !== tv.op || document.hidden) return;
    try {
      api.tvwindow.show(function () {
        if (!done(token)) return;
        tv.shown = true;
        log('HDMI ' + source.hdmi + ' visas');
        setSource({ ok: true });
      }, function (err) { fail(token, 'show', err); }, percent(tv.rect), 'MAIN', 'BEHIND');
    } catch (err) { fail(token, 'show', err); }
  }
  function select(i) {
    if (tv.busy || !tv.sources.length) return;
    const chosen = (i + tv.sources.length) % tv.sources.length;
    const s = tv.sources[chosen];
    const token = begin();
    log('Väljer HDMI ' + s.number + '…');
    try {
      api.tvwindow.setSource(s, function () {
        if (token !== tv.op) return;
        tv.index = chosen;
        source.hdmi = Number(s.number);
        showWindow(token);
      }, function (err) { fail(token, 'setSource', err); }, 'MAIN');
    } catch (err) { fail(token, 'setSource', err); }
  }
  function scan() {
    if (!realTV || tv.busy) return;
    const token = begin();
    tv.shown = false;
    try {
      api.systeminfo.getPropertyValue('VIDEOSOURCE', function (result) {
        if (!done(token)) return;
        const connected = result.connected || [];
        tv.sources = connected.filter(function (s) { return s.type === 'HDMI'; });
        log('Källor: ' + connected.map(function (s) { return s.type + ' ' + s.number; }).join(', '));
        const i = tv.sources.findIndex(function (s) { return Number(s.number) === settings.hdmi; });
        if (i < 0) {
          setSource({ ok: false, error: 'HDMI ' + settings.hdmi + ' hittades inte, är boxen på?' });
          return;
        }
        select(i);
      }, function (err) { fail(token, 'VIDEOSOURCE', err); });
    } catch (err) { fail(token, 'VIDEOSOURCE', err); }
  }

  /** HDMI that went away (the box switched off) comes back by itself: the TV reports a
   * change of its sources, and while there is no picture we look again every 10 s. */
  function watchSources() {
    if (!realTV) return;
    try {
      api.systeminfo.addPropertyValueChangeListener('VIDEOSOURCE', function () {
        if (document.hidden) return;
        log('Källorna ändrades');
        tv.busy = false;
        scan();
      });
    } catch (err) { log('VIDEOSOURCE-lyssnare: ' + err); }
    setInterval(function () {
      if (!document.hidden && !source.ok && !tv.busy) scan();
    }, 10000);
  }

  /** The overlay asks to move the TV picture; answer when it has moved. */
  function placeWindow(rect, id) {
    tv.rect = rect || null;
    const t0 = performance.now();
    const reply = function (ok, error) {
      toOverlay({ t: 'window_done', id: id, ok: ok, ms: performance.now() - t0, error: error || null, preview: !realTV });
    };
    if (!realTV) {
      const r = rect || [0, 0, W, H];
      const box = $('preview-video').style;
      box.left = r[0] + 'px'; box.top = r[1] + 'px'; box.width = r[2] + 'px'; box.height = r[3] + 'px';
      return reply(true);
    }
    if (!tv.shown) return reply(false, 'ingen HDMI-bild visas ännu');
    try {
      api.tvwindow.show(function () { reply(true); }, function (err) {
        reply(false, (err.name || 'Error') + ' – ' + (err.message || String(err)));
      }, percent(tv.rect), 'MAIN', 'BEHIND');
    } catch (err) { reply(false, String(err)); }
  }

  // ---- the overlay -----------------------------------------------------------------------

  function info() {
    const out = { t: 'info', version: VERSION, tv: realTV, mode: settings.mode, hdmi: source.hdmi, server: base,
      source: { hdmi: source.hdmi, ok: source.ok, error: source.error || null } };
    try { out.platform = api.systeminfo.getCapability('http://tizen.org/feature/platform.version'); } catch (err) { /* computer */ }
    try { out.model = window.webapis.productinfo.getModel(); } catch (err) { /* computer or no webapis */ }
    try { out.firmware = window.webapis.productinfo.getFirmware(); } catch (err) { /* computer or no webapis */ }
    out.screen_saver = screenSaver;
    return out;
  }
  function toOverlay(message) {
    message.to = 'overlay';
    if (settings.mode === 'direct') window.postMessage(message, '*');
    else if (overlayOrigin() && iframe.contentWindow) iframe.contentWindow.postMessage(message, overlayOrigin());
  }
  function overlayOrigin() {
    try { return base ? new URL(base).origin : null; } catch (err) { return null; }
  }

  window.addEventListener('message', function (event) {
    const m = event.data;
    if (!m || m.to !== 'shell') return;
    if (settings.mode === 'direct' ? event.source !== window
      : event.source !== iframe.contentWindow || event.origin !== overlayOrigin()) return;
    if (m.t === 'hello') toOverlay(info());
    else if (m.t === 'ready') {
      lastReady = Date.now();
      reloading = false;
      overlayReady = true;
      if (settings.mode !== 'direct') iframe.classList.remove('hidden');
      clearTimeout(readyTimer);
      clearTimeout(retryTimer);
      $('status').classList.add('hidden');
      $('diag').classList.add('hidden');
    } else if (m.t === 'window') placeWindow(m.rect, m.id);
    else if (m.t === 'exit') exit();
    else if (m.t === 'setup') openSetup();
    else if (m.t === 'hdmi') { log('Visar HDMI igen'); tv.busy = false; scan(); }
  });

  function connect() {
    clearTimeout(retryTimer);
    if (!settings.server) { openSetup(); return; }
    base = serverBase(settings.server);
    status('Ansluter till ' + settings.server + '…', 'OK: inställningar');
    const controller = 'AbortController' in window ? new AbortController() : null;
    const timeout = setTimeout(function () { if (controller) controller.abort(); }, 5000);
    fetch(base + '/api/health', { cache: 'no-store', signal: controller ? controller.signal : undefined })
      .then(function (r) { if (!r.ok) throw new Error('HTTP ' + r.status); return r.json(); })
      .then(function (body) {
        clearTimeout(timeout);
        log('Servern svarar, version ' + body.version);
        loadOverlay();
      })
      .catch(function (err) {
        clearTimeout(timeout);
        log('Ingen kontakt med ' + base + ': ' + err);
        status('Ingen kontakt med ' + settings.server, 'Försöker igen om 5 s · OK: inställningar · Back: avsluta');
        retryTimer = setTimeout(connect, 5000);
      });
  }

  function loadOverlay() {
    status('Laddar grafiken från servern…', settings.mode === 'direct' ? 'Läge: direkt' : 'Läge: iframe');
    if (settings.mode === 'direct') {
      const script = document.createElement('script');
      script.type = 'module';
      script.src = base + '/tv/tv.js';
      script.onerror = function () { status('Kunde inte ladda ' + script.src, 'Prova läge iframe · OK: inställningar'); };
      document.body.appendChild(script);
      readyTimer = setTimeout(function () {
        if (!overlayReady) status('Grafiken startar inte', 'Prova läge iframe · OK: inställningar · Back: avsluta');
      }, SILENT_MS);
    } else {
      iframe.src = base + '/tv/';
      iframe.classList.remove('hidden');
      lastReady = Date.now(); // a grace period for the first start
      setInterval(watchOverlay, 5000);
    }
  }

  /** The heartbeat stopped: wait for the service, then load the graphics again. */
  function watchOverlay() {
    if (reloading || document.hidden || Date.now() - lastReady < SILENT_MS) return;
    reloading = true;
    overlayReady = false;
    iframe.classList.add('hidden'); // an error page would cover the TV picture
    placeWindow(null, 0); // the whole TV picture until the graphics are back and place it
    status('Grafiken svarar inte', 'Väntar på servern och försöker igen · OK: inställningar');
    reloadWhenUp();
  }

  function reloadWhenUp() {
    clearTimeout(retryTimer);
    fetch(base + '/api/health', { cache: 'no-store' })
      .then(function (r) { if (!r.ok) throw new Error('HTTP ' + r.status); })
      .then(function () {
        log('Servern svarar igen, laddar grafiken');
        lastReady = Date.now(); // the reload's own grace period
        reloading = false;
        iframe.src = base + '/tv/?t=' + Date.now();
      })
      .catch(function (err) {
        log('Väntar på servern: ' + err);
        retryTimer = setTimeout(reloadWhenUp, 5000);
      });
  }

  // ---- screen saver ---------------------------------------------------------------------
  // The TV counts an app nobody presses keys in as idle and starts its screen saver after a
  // while; on a TV input it never does (seen 2026-10-31). Off while the app is shown, back
  // on when it is hidden or exits. Samsung's AppCommon API first, Tizen's power lock as well.
  let screenSaver = realTV ? 'okänd' : 'dator';
  function setScreenSaver(off) {
    if (!realTV) return;
    try {
      if (off) api.power.request('SCREEN', 'SCREEN_NORMAL');
      else api.power.release('SCREEN');
    } catch (err) { log('power: ' + err); }
    const common = window.webapis && window.webapis.appcommon;
    if (!common) { screenSaver = 'appcommon saknas'; log('Skärmsläckare: appcommon saknas'); return; }
    const states = common.AppCommonScreenSaverState;
    try {
      common.setScreenSaver(off ? states.SCREEN_SAVER_OFF : states.SCREEN_SAVER_ON, function () {
        screenSaver = off ? 'av' : 'på';
      }, function (err) {
        screenSaver = 'fel: ' + (err.message || err);
        log('setScreenSaver: ' + (err.message || err));
      });
    } catch (err) {
      screenSaver = 'fel: ' + err;
      log('setScreenSaver: ' + err);
    }
  }

  function exit() {
    tv.op++;
    clearTimeout(tv.timer);
    if (!realTV) { log('På TV:n avslutar detta appen.'); return; }
    setScreenSaver(false);
    try { api.application.getCurrentApplication().exit(); } catch (err) { log('exit: ' + err); }
  }

  // ---- settings screen ------------------------------------------------------------------

  const FIELDS = ['server', 'hdmi', 'mode', 'connect'];
  const MODES = { iframe: 'Iframe', direct: 'Direkt (reserv)' };
  let focus = 0;
  let draft = null;

  function openSetup() {
    draft = Object.assign({}, settings);
    $('server').value = draft.server;
    focus = draft.server ? FIELDS.indexOf('connect') : 0;
    $('setup-error').textContent = '';
    renderSetup();
    $('setup').classList.remove('hidden');
  }
  function closeSetup() {
    $('server').blur();
    $('setup').classList.add('hidden');
  }
  function renderSetup() {
    $('hdmi').textContent = 'HDMI ' + draft.hdmi;
    $('mode').textContent = MODES[draft.mode];
    document.querySelectorAll('.field').forEach(function (f) {
      f.classList.toggle('focus', f.dataset.field === FIELDS[focus]);
    });
  }
  function setupKey(key) {
    const field = FIELDS[focus];
    if (key === 'up' || key === 'down') {
      $('server').blur();
      focus = (focus + (key === 'up' ? FIELDS.length - 1 : 1)) % FIELDS.length;
    } else if (key === 'left' || key === 'right') {
      const step = key === 'left' ? -1 : 1;
      if (field === 'hdmi') draft.hdmi = ((draft.hdmi - 1 + step + 4) % 4) + 1;
      if (field === 'mode') draft.mode = draft.mode === 'iframe' ? 'direct' : 'iframe';
    } else if (key === 'ok') {
      if (field === 'server') $('server').focus();
      else if (field === 'connect') return apply();
      else focus = FIELDS.indexOf('connect');
    } else if (key === 'back') {
      if (settings.server) closeSetup();
      else exit();
      return;
    }
    renderSetup();
  }
  function apply() {
    draft.server = $('server').value.trim();
    if (!draft.server) { $('setup-error').textContent = 'Skriv in serverns adress, t.ex. 192.168.1.20:8010'; return; }
    const changed = draft.server !== settings.server || draft.mode !== settings.mode || draft.hdmi !== settings.hdmi;
    settings = draft;
    saveSettings();
    closeSetup();
    if (changed && (overlayReady || base)) { location.reload(); return; }
    if (!overlayReady) connect();
  }

  // ---- keys -------------------------------------------------------------------------------

  function registerKeys() {
    if (!realTV || !api.tvinputdevice) return;
    let keys = [];
    try { keys = api.tvinputdevice.getSupportedKeys(); } catch (err) { log('getSupportedKeys: ' + err); }
    keys.forEach(function (k) {
      if (KEEP_FOR_TV.test(k.name)) return;
      try { api.tvinputdevice.registerKey(k.name); supported[k.code] = k.name; }
      catch (err) { log('registerKey ' + k.name + ': ' + err); }
    });
    log(Object.keys(supported).length + ' knappar registrerade');
  }

  document.addEventListener('keydown', function (event) {
    const code = event.keyCode;
    const typing = document.activeElement === $('server');
    if (typing) {
      // the input has the keyboard: only leave it on Enter, Done, Cancel or up/down
      if (code === 13 || code === IME_DONE || code === IME_CANCEL || code === 38 || code === 40 || code === 27) {
        event.preventDefault();
        $('server').blur();
        draft.server = $('server').value.trim();
        if (code === 38 || code === 40) setupKey(code === 38 ? 'up' : 'down');
        else { focus = FIELDS.indexOf('hdmi'); renderSetup(); }
      }
      return;
    }
    const key = KEYS[code] || supported[code];
    if (!key) return;
    event.preventDefault();
    if (event.repeat) return;
    if (!$('setup').classList.contains('hidden')) return setupKey(key);
    if (overlayReady) return toOverlay({ t: 'key', key: key, code: code });
    if (key === 'ok') openSetup();
    else if (key === 'back') exit();
  });

  document.addEventListener('visibilitychange', function () {
    if (!realTV) return;
    if (document.hidden) {
      tv.op++;
      clearTimeout(tv.timer);
      tv.busy = false;
      tv.shown = false;
      try { api.tvwindow.hide(function () {}, function (err) { log('hide: ' + err.message); }, 'MAIN'); }
      catch (err) { log('hide: ' + err); }
      setScreenSaver(false);
    } else {
      setScreenSaver(true);
      scan();
    }
  });

  // ---- start ------------------------------------------------------------------------------

  if (!realTV) document.body.classList.add('preview');
  fit();
  window.addEventListener('resize', fit);
  log('SHL live! ' + VERSION + (realTV ? ' på TV:n' : ' (förhandsvisning på dator)'));
  registerKeys();
  watchSources();
  setScreenSaver(true);
  // said again now and then, in case the TV forgets it (no harm when it holds)
  setInterval(function () { if (!document.hidden) setScreenSaver(true); }, 5 * 60 * 1000);
  scan();
  connect();
}());
