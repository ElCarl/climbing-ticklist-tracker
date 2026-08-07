/* Enchainment page: stage/pitch ticks, decisions, walk pacing, profile. */
(() => {
  'use strict';

  const DATA = JSON.parse(document.getElementById('challenge-data').textContent);
  const KEY = `ticklist:${DATA.slug}:v1`;
  const THEME_KEY = 'ticklist:theme';
  const byId = Object.fromEntries(DATA.stages.map(s => [s.id, s]));

  if ('serviceWorker' in navigator && location.hostname !== 'localhost') {
    navigator.serviceWorker.register('../sw.js');
  }

  const load = () => {
    try {
      return JSON.parse(localStorage.getItem(KEY)) ||
        { stages: {}, pitches: {}, choices: {} };
    } catch { return { stages: {}, pitches: {}, choices: {} }; }
  };
  let state = load();
  const save = () => localStorage.setItem(KEY, JSON.stringify(state));

  const initials = name => name.split(/\s+/).map(w => w[0]).join('');
  const fmtTime = ms => new Date(ms).toLocaleTimeString('en-GB',
    { hour: '2-digit', minute: '2-digit' });
  const fmtDur = mins => {
    const m = Math.round(mins);
    return m >= 60 ? `${Math.floor(m / 60)}h${String(m % 60).padStart(2, '0')}` : `${m}m`;
  };

  const choiceOf = did => state.choices[did] ?? 0;

  function visibleStages() {
    return DATA.stages.filter(s =>
      !s.branch || choiceOf(s.branch.decision) === s.branch.option);
  }

  function stageDone(id) { return !!state.stages[id]; }

  function applyBranches() {
    document.querySelectorAll('[data-branch]').forEach(el => {
      const [did, opt] = el.dataset.branch.split(':');
      el.hidden = choiceOf(did) !== Number(opt);
    });
    document.querySelectorAll('.decision-opt').forEach(btn => {
      btn.classList.toggle('selected',
        choiceOf(btn.dataset.decision) === Number(btn.dataset.option));
    });
  }

  function markPitch(stageId, pitchIdx, leader) {
    const stage = byId[stageId];
    const ticks = state.pitches[stageId] = state.pitches[stageId] || {};
    const t = Date.now();
    for (let i = 1; i < pitchIdx; i++) {
      if (!ticks[i]) ticks[i] = { implied: true };
    }
    ticks[pitchIdx] = { t, leader };
    if (stage.pitches.every(p => ticks[p.i])) state.stages[stageId] = { t };
    save(); render();
  }

  function tickRoute(stageId) {
    const stage = byId[stageId];
    const ticks = state.pitches[stageId] = state.pitches[stageId] || {};
    const t = Date.now();
    for (const p of stage.pitches) if (!ticks[p.i]) ticks[p.i] = { implied: true };
    state.stages[stageId] = { t };
    save(); render();
  }

  function prevTimestamp(stageId) {
    const seq = visibleStages();
    let last = null;
    for (const s of seq) {
      if (s.id === stageId) break;
      if (state.stages[s.id]) last = state.stages[s.id].t;
      for (const p of Object.values(state.pitches[s.id] || {})) {
        if (p.t && (!last || p.t > last)) last = p.t;
      }
    }
    return last;
  }

  function render() {
    applyBranches();

    for (const s of DATA.stages) {
      const card = document.querySelector(`[data-stage="${s.id}"]`);
      if (!card || card.classList.contains('decision')) continue;
      const done = stageDone(s.id);
      card.classList.toggle('done', done);
      const status = card.querySelector(`.status[data-stage="${s.id}"]`);
      const tickBtn = card.querySelector('.tick');
      const clearBtn = card.querySelector('.clear');
      if (done) {
        const t = state.stages[s.id].t;
        let text = `✓ ${fmtTime(t)}`;
        const prev = prevTimestamp(s.id);
        if (s.kind !== 'climb' && prev && t > prev) {
          text += ` · took ${fmtDur((t - prev) / 60000)} (est ${s.estimateMin}m)`;
        }
        status.textContent = text;
        tickBtn.hidden = true; clearBtn.hidden = false;
      } else {
        status.textContent = '';
        tickBtn.hidden = false; clearBtn.hidden = true;
      }
      if (s.kind === 'climb') {
        for (const p of s.pitches) {
          const el = card.querySelector(
            `.pitch-status[data-stage="${s.id}"][data-pitch="${p.i}"]`);
          const tick = (state.pitches[s.id] || {})[p.i];
          const row = card.querySelector(
            `.pitch[data-stage="${s.id}"][data-pitch="${p.i}"]`);
          row.classList.toggle('done', !!tick);
          el.textContent = !tick ? '' :
            tick.implied ? '✓' : `✓ ${fmtTime(tick.t)} ${initials(tick.leader)}`;
        }
      }
    }
    renderPacing();
    renderProfile();
  }

  function renderPacing() {
    const seq = visibleStages();
    const done = seq.filter(s => stageDone(s.id));
    document.getElementById('progress').textContent =
      `${done.length}/${seq.length} stages`;

    const pacing = document.getElementById('pacing');
    const times = [];
    for (const s of seq) {
      if (state.stages[s.id]) times.push(state.stages[s.id].t);
      for (const p of Object.values(state.pitches[s.id] || {})) if (p.t) times.push(p.t);
    }
    if (!times.length) { pacing.hidden = true; return; }
    const dayStart = Math.min(...times);
    const lastEvent = Math.max(...times);
    const now = Date.now();
    const doneEst = done.reduce((a, s) => a + s.estimateMin, 0);
    const remEst = seq.filter(s => !stageDone(s.id))
      .reduce((a, s) => a + s.estimateMin, 0);
    let factor = 1;
    if (doneEst > 0 && lastEvent > dayStart) {
      factor = Math.min(2.5, Math.max(0.5, (lastEvent - dayStart) / 60000 / doneEst));
    }
    const target = dayStart + DATA.targetHours * 3600000;
    let text = `Started ${fmtTime(dayStart)} · ${fmtDur((now - dayStart) / 60000)} in`;
    if (remEst > 0) {
      const projected = now + remEst * factor * 60000;
      const delta = (target - projected) / 60000;
      text += ` · pace ×${factor.toFixed(2)} · projected finish ${fmtTime(projected)} ` +
        (delta >= 0 ? `(${fmtDur(delta)} inside target)` : `(${fmtDur(-delta)} over target)`);
    } else {
      text += ' · finished 🏁';
    }
    pacing.textContent = text;
    pacing.hidden = false;
  }

  function renderProfile() {
    const lines = document.querySelectorAll('.profile-path');
    let active = null;
    lines.forEach(line => {
      const choice = JSON.parse(line.dataset.choice);
      const match = Object.entries(choice).every(([d, o]) => choiceOf(d) === o);
      line.classList.toggle('active', match);
      if (match) active = line;
    });
    const dot = document.getElementById('profile-dot');
    if (!active) { dot.setAttribute('r', 0); return; }
    const ids = JSON.parse(active.dataset.ids);
    const pts = active.getAttribute('points').trim().split(/\s+/)
      .map(p => p.split(',').map(Number));
    let idx = 0;
    for (const [i, id] of ids.entries()) if (stageDone(id)) idx = i + 1;
    const [cx, cy] = pts[Math.min(idx, pts.length - 1)];
    dot.setAttribute('r', 5);
    dot.setAttribute('cx', cx);
    dot.setAttribute('cy', cy);
  }

  document.querySelectorAll('.pitch-lead').forEach(btn => btn.addEventListener('click',
    () => markPitch(btn.dataset.stage, Number(btn.dataset.pitch), btn.dataset.leader)));

  document.querySelectorAll('.tick-route').forEach(btn => btn.addEventListener('click',
    () => tickRoute(btn.dataset.stage)));

  document.querySelectorAll('.arrive').forEach(btn => btn.addEventListener('click', () => {
    state.stages[btn.dataset.stage] = { t: Date.now() };
    save(); render();
  }));

  document.querySelectorAll('.clear').forEach(btn => btn.addEventListener('click', () => {
    const id = btn.dataset.stage;
    if (confirm(`Clear ${byId[id].name}?`)) {
      delete state.stages[id];
      delete state.pitches[id];
      save(); render();
    }
  }));

  document.querySelectorAll('.decision-opt').forEach(btn => btn.addEventListener('click',
    () => {
      state.choices[btn.dataset.decision] = Number(btn.dataset.option);
      save(); render();
    }));

  document.getElementById('clear-all').addEventListener('click', () => {
    const n = Object.keys(state.stages).length + Object.keys(state.pitches).length;
    if (!n) return;
    if (confirm("Clear the whole day's log (all stages and pitches)?")) {
      state = { stages: {}, pitches: {}, choices: state.choices };
      save(); render();
    }
  });

  // Export
  const dialog = document.getElementById('export-dialog');
  document.getElementById('export').addEventListener('click', () => {
    const lines = [`${DATA.name} — ${new Date().toLocaleDateString('en-GB')}`];
    for (const s of visibleStages()) {
      const st = state.stages[s.id];
      if (s.kind === 'climb') {
        const ticks = state.pitches[s.id] || {};
        if (!st && !Object.keys(ticks).length) continue;
        lines.push(`${s.name}${st ? ` — topped out ${fmtTime(st.t)}` : ' — in progress'}`);
        for (const p of s.pitches) {
          const t = ticks[p.i];
          if (!t) continue;
          lines.push(t.implied ? `  P${p.i} ✓` :
            `  P${p.i} ✓ ${fmtTime(t.t)} led ${t.leader}`);
        }
      } else if (st) {
        lines.push(`${s.name} — ${fmtTime(st.t)}`);
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
