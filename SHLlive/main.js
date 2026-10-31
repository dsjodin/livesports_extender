(function () {
  'use strict';
  var sources = [], index = -1, busy = false, lines = [], operation = 0, timer;
  var api = window.tizen;
  var realTV = !!(api && api.tvwindow && api.systeminfo);

  function log(message) {
    lines.push(message);
    if (lines.length > 8) lines.shift();
    document.getElementById('log').textContent = lines.join('\n');
    console.log(message);
  }
  function error(where, err) {
    document.getElementById('diagnostics').classList.remove('hidden');
    log(where + ': ' + (err.name || 'Error') + ' – ' + (err.message || String(err)));
  }
  function start() {
    busy = true;
    var token = ++operation;
    clearTimeout(timer);
    timer = setTimeout(function () {
      if (token !== operation) return;
      operation++;
      busy = false;
      error('Timeout', {message: 'Inget svar inom 10 s. Tryck ↓ för att försöka igen.'});
    }, 10000);
    return token;
  }
  function done(token) {
    if (token !== operation) return false;
    clearTimeout(timer);
    busy = false;
    return true;
  }
  function fail(token, where, err) {
    if (done(token)) error(where, err);
  }
  function show(token) {
    if (token !== operation || document.hidden) return;
    try {
      api.tvwindow.show(function () {
        if (!done(token)) return;
        log('show(BEHIND) OK. Kontrollera att HDMI-bild och ljud faktiskt fungerar.');
      }, function (err) { fail(token, 'show(BEHIND)', err); },
      ['0%', '0%', '100%', '100%'], 'MAIN', 'BEHIND');
    } catch (err) { fail(token, 'show(BEHIND)', err); }
  }
  function select(next) {
    if (busy || !sources.length) return;
    var selected = (next + sources.length) % sources.length;
    var source = sources[selected];
    var token = start();
    log('Väljer HDMI ' + source.number + '…');
    try {
      api.tvwindow.setSource(source, function () {
        if (token !== operation) return;
        index = selected;
        document.getElementById('source').textContent = 'HDMI ' + source.number;
        log('setSource OK');
        show(token);
      }, function (err) { fail(token, 'setSource', err); }, 'MAIN');
    } catch (err) { fail(token, 'setSource', err); }
  }
  function scan() {
    if (!realTV) { log('Datorläge: HDMI kan bara testas på TV:n.'); return; }
    if (busy) return;
    var token = start();
    log('Söker bildkällor…');
    try {
      api.systeminfo.getPropertyValue('VIDEOSOURCE', function (result) {
        if (!done(token)) return;
        sources = (result.connected || []).filter(function (s) { return s.type === 'HDMI'; });
        index = -1;
        document.getElementById('source').textContent = 'Ingen källa vald';
        log('Rapporterade källor: ' + (result.connected || []).map(function (s) {
          return s.type + ' ' + s.number;
        }).join(', '));
        if (!sources.length) { log('Ingen HDMI hittades. Slå på boxen och tryck ↓ för att söka igen.'); return; }
        var chosen = -1;
        sources.forEach(function (s, i) {
          if (Number(s.number) === 1) chosen = i;
        });
        if (chosen < 0) {
          log('HDMI 1 hittades inte. Slå på Telia-boxen och tryck ↓, eller välj annan HDMI med ← / →.');
          return;
        }
        select(chosen);
      }, function (err) { fail(token, 'VIDEOSOURCE', err); });
    } catch (err) { fail(token, 'VIDEOSOURCE', err); }
  }
  function exit() {
    operation++;
    clearTimeout(timer);
    if (!realTV) { log('På TV:n avslutar Back appen.'); return; }
    try { api.application.getCurrentApplication().exit(); }
    catch (err) { error('exit', err); }
  }
  document.addEventListener('keydown', function (event) {
    var key = event.keyCode;
    if ([13,37,38,39,40,10009,27].indexOf(key) < 0) return;
    event.preventDefault();
    if (event.repeat) return;
    if (key === 13) {
      document.getElementById('overlay').classList.toggle('hidden');
      document.getElementById('alpha-test').classList.toggle('hidden');
    }
    if (key === 38) document.getElementById('diagnostics').classList.toggle('hidden');
    if (key === 37) select(index < 0 ? sources.length - 1 : index - 1);
    if (key === 39) select(index + 1);
    if (key === 40) scan();
    if (key === 10009 || key === 27) exit();
  });
  document.addEventListener('visibilitychange', function () {
    if (!realTV) return;
    if (document.hidden) {
      operation++;
      clearTimeout(timer);
      busy = false;
      try { api.tvwindow.hide(function () {}, function (err) { error('hide', err); }, 'MAIN'); }
      catch (err) { error('hide', err); }
    } else { scan(); }
  });
  if (!realTV) document.body.classList.add('preview');
  log(realTV ? 'Tizen TVWindow finns. Startar HDMI-test.' : 'Förhandsvisning: ingen anslutning till TV eller HDMI.');
  scan();
}());
