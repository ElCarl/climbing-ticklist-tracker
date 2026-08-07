/* Ticklist challenge page: tick state, pacing, export, theme, topo zoom. */
(() => {
  'use strict';

  const DATA = JSON.parse(document.getElementById('challenge-data').textContent);
  const KEY = `ticklist:${DATA.slug}:v1`;
  const THEME_KEY = 'ticklist:theme';
  const bySlug = Object.fromEntries(DATA.routes.map(r => [r.slug, r]));

  if ('serviceWorker' in navigator && location.hostname !== 'localhost') {
    navigator.serviceWorker.register('../sw.js');
  }

  const load = () => {
    try { return JSON.parse(localStorage.getItem(KEY)) || { ticks: {} }; }
    catch { return { ticks: {} }; }
  };
  let state = load();
  const save = () => localStorage.setItem(KEY, JSON.stringify(state));

  const fmtTime = ms => new Date(ms).toLocaleTimeString('en-GB',
    { hour: '2-digit', minute: '2-digit' });
  const fmtDur = mins => {
    const m = Math.round(mins);
    return m >= 60 ? `${Math.floor(m / 60)}h${String(m % 60).padStart(2, '0')}` : `${m}m`;
  };

  function render() {
    for (const r of DATA.routes) {
      const card = document.querySelector(`[data-route="${r.slug}"]`);
      const status = card.querySelector('.status');
      const tick = card.querySelector('.tick');
      const skip = card.querySelector('.skip');
      const clear = card.querySelector('.clear');
      const t = state.ticks[r.slug];
      card.classList.toggle('done', t?.state === 'led');
      card.classList.toggle('skipped', t?.state === 'skipped');
      if (t?.state === 'led') {
        status.textContent = `✓ ${fmtTime(t.t)}`;
        tick.hidden = skip.hidden = true;
        clear.hidden = false;
      } else if (t?.state === 'skipped') {
        status.textContent = '– skipped';
        tick.hidden = skip.hidden = true;
        clear.hidden = false;
      } else {
        status.textContent = '';
        tick.hidden = skip.hidden = false;
        clear.hidden = true;
      }
    }
    renderPacing();
  }

  function renderPacing() {
    const ticks = Object.values(state.ticks);
    const led = ticks.filter(t => t.state === 'led');
    const skipped = ticks.filter(t => t.state === 'skipped');
    const total = DATA.routes.length;
    const progress = document.getElementById('progress');
    progress.textContent = `${led.length}/${total}` +
      (skipped.length ? ` · ${skipped.length} skipped` : '');

    const pacing = document.getElementById('pacing');
    if (!led.length) { pacing.hidden = true; return; }
    const start = Math.min(...led.map(t => t.t));
    const now = Date.now();
    const elapsedMin = (now - start) / 60000;
    const remaining = total - led.length - skipped.length;
    const perRoute = elapsedMin / led.length;
    const target = start + DATA.targetHours * 3600000;
    let text = `Started ${fmtTime(start)} · ${fmtDur(elapsedMin)} in · ` +
      `${fmtDur(perRoute)}/route`;
    if (remaining > 0) {
      const projected = now + remaining * perRoute * 60000;
      const delta = (target - projected) / 60000;
      text += ` · projected finish ${fmtTime(projected)} ` +
        (delta >= 0 ? `(${fmtDur(delta)} inside target)` : `(${fmtDur(-delta)} over target)`);
    } else {
      text += ' · finished 🏁';
    }
    pacing.textContent = text;
    pacing.hidden = false;
  }

  function highlightTransition(slug) {
    const row = document.querySelector(`[data-transition-after="${slug}"]`);
    if (!row) return;
    row.classList.remove('flash');
    void row.offsetWidth;
    row.classList.add('flash');
    row.scrollIntoView({ behavior: 'smooth', block: 'center' });
  }

  document.querySelectorAll('.tick').forEach(btn => btn.addEventListener('click', () => {
    const slug = btn.dataset.slug;
    state.ticks[slug] = { state: 'led', t: Date.now(), leader: bySlug[slug].leader };
    save(); render(); highlightTransition(slug);
  }));

  document.querySelectorAll('.skip').forEach(btn => btn.addEventListener('click', () => {
    const slug = btn.dataset.slug;
    state.ticks[slug] = { state: 'skipped', t: Date.now() };
    save(); render();
  }));

  document.querySelectorAll('.clear').forEach(btn => btn.addEventListener('click', () => {
    const slug = btn.dataset.slug;
    if (!state.ticks[slug]) return;
    if (confirm(`Clear ${bySlug[slug].name}?`)) {
      delete state.ticks[slug];
      save(); render();
    }
  }));

  document.getElementById('clear-all').addEventListener('click', () => {
    const n = Object.keys(state.ticks).length;
    if (!n) return;
    if (confirm(`Clear all ${n} ticked/skipped routes? This wipes the day's log.`)) {
      state = { ticks: {} };
      save(); render();
    }
  });

  // Export
  const dialog = document.getElementById('export-dialog');
  document.getElementById('export').addEventListener('click', () => {
    const lines = [`${DATA.name} — ${new Date().toLocaleDateString('en-GB')}`];
    for (const r of DATA.routes) {
      const t = state.ticks[r.slug];
      if (t?.state === 'led') {
        lines.push(`${r.number}. ${r.name} (${r.grade}) — ${fmtTime(t.t)} — led ${t.leader || '?'}`);
      } else if (t?.state === 'skipped') {
        lines.push(`${r.number}. ${r.name} (${r.grade}) — skipped`);
      }
    }
    if (lines.length === 1) lines.push('Nothing ticked yet.');
    document.getElementById('export-text').value = lines.join('\n');
    dialog.showModal();
  });
  document.getElementById('export-close').addEventListener('click', () => dialog.close());
  document.getElementById('export-copy').addEventListener('click', () => {
    navigator.clipboard.writeText(document.getElementById('export-text').value);
  });

  // Theme
  const applyTheme = t => document.documentElement.dataset.theme = t;
  const savedTheme = localStorage.getItem(THEME_KEY);
  if (savedTheme) applyTheme(savedTheme);
  document.getElementById('theme-toggle').addEventListener('click', () => {
    const cur = document.documentElement.dataset.theme ||
      (matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light');
    const next = cur === 'dark' ? 'light' : 'dark';
    applyTheme(next);
    localStorage.setItem(THEME_KEY, next);
  });

  // Topo zoom
  const overlay = document.getElementById('topo-overlay');
  const full = document.getElementById('topo-full');
  document.querySelectorAll('.topo').forEach(img => img.addEventListener('click', () => {
    full.src = img.src;
    overlay.hidden = false;
  }));
  document.getElementById('topo-close').addEventListener('click', () => overlay.hidden = true);

  render();
  setInterval(renderPacing, 30000);
})();
