// ClaimRight API client. Endpoints follow CLAIMRIGHT_APP_PROMPT.md.
// The app uses this for every non-demo case. Demo mode never calls it (it reads claimright-data.js).
(function () {
  // Served by the ClaimRight backend itself (Cloud Run or the laptop backup): call the same server.
  // Opened from disk or another host: fall back to the live Cloud Run API.
  var CLOUD_RUN = 'https://claimright-809314822230.us-central1.run.app';
  var sameOrigin = /^https?:$/.test(location.protocol) &&
    (/\.run\.app$/.test(location.hostname) || /^(localhost|127\.0\.0\.1)$/.test(location.hostname));
  var DEFAULT_BASE = sameOrigin ? location.origin : CLOUD_RUN;
  var LS = 'claimright_api_base';
  function base() { return (localStorage.getItem(LS) || DEFAULT_BASE).replace(/\/+$/, ''); }

  async function req(method, path, opts) {
    opts = opts || {};
    var ctl = new AbortController();
    var tm = setTimeout(function () { ctl.abort(); }, opts.timeout || 90000);
    try {
      var init = { method: method, signal: ctl.signal, headers: {} };
      if (opts.json !== undefined) { init.headers['Content-Type'] = 'application/json'; init.body = JSON.stringify(opts.json); }
      else if (opts.form) { init.body = opts.form; }
      else if (method === 'POST') { init.headers['Content-Type'] = 'application/json'; init.body = '""'; }
      var r = await fetch(base() + path, init);
      if (!r.ok) {
        var detail = '';
        try { var j = await r.json(); detail = j.detail || j.error || ''; } catch (e) {}
        throw new Error((detail ? detail + ' ' : '') + '(HTTP ' + r.status + ')');
      }
      return await r.json();
    } catch (e) {
      if (e.name === 'AbortError') throw new Error('Request timed out');
      throw e;
    } finally { clearTimeout(tm); }
  }
  var enc = encodeURIComponent;

  var live = {
    health: function () { return req('GET', '/api/health', { timeout: 10000 }); },
    demoCases: function () { return req('GET', '/api/demo-cases'); },
    demo: function (id) { return req('POST', '/api/demo/' + enc(id)); },
    // files: { bill: File, settlement: File, policy: File } — PDF/JPG/PNG/WebP, ≤15 MB each
    audit: function (files) {
      var f = new FormData();
      ['bill', 'settlement', 'policy'].forEach(function (k) { f.append(k, files[k]); });
      return req('POST', '/api/audit', { form: f, timeout: 120000 });
    },
    report: function (id) { return req('GET', '/api/report/' + enc(id)); },
    letter: function (id, lang) { return req('POST', '/api/letter/' + enc(id) + '?lang=' + lang); },
    chat: function (id, message, sessionId) { return req('POST', '/api/chat/' + enc(id), { json: { message: message, session_id: sessionId || null }, timeout: 60000 }); },
    rules: function () { return req('GET', '/api/rules'); },
    // TODO(backend): no payment endpoint yet. Replace with the real payment call; resolve {ok:true} on success.
    pay: function (caseId, amount) { return Promise.resolve({ ok: true, stub: true }); }
  };

  window.ClaimRightAPI = {
    live: live,
    DEFAULT_BASE: DEFAULT_BASE,
    getBase: base,
    setBase: function (v) { if (v && v.trim()) localStorage.setItem(LS, v.trim()); else localStorage.removeItem(LS); }
  };
})();
