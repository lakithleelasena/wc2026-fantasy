/* ── WC 2026 Fantasy – Frontend ─────────────────────────────────────────── */

// ── Tab navigation ────────────────────────────────────────────────────────
document.querySelectorAll('.tab').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
    document.querySelectorAll('.tab-content').forEach(s => s.classList.add('hidden'));
    btn.classList.add('active');
    document.getElementById('tab-' + btn.dataset.tab).classList.remove('hidden');

    if (btn.dataset.tab === 'players' && !playersLoaded) loadPlayers();
    if (btn.dataset.tab === 'fixtures' && !fixturesLoaded) loadFixtures();
  });
});

// ── Slider labels ─────────────────────────────────────────────────────────
function bindSlider(id, displayId, divisor = 1) {
  const el = document.getElementById(id);
  const display = document.getElementById(displayId);
  el.addEventListener('input', () => {
    display.textContent = divisor === 10
      ? (el.value / 10).toFixed(1)
      : parseFloat(el.value).toFixed(2);
  });
}
bindSlider('budget', 'budget-display', 10);
bindSlider('w-ts', 'w-ts-display');
bindSlider('w-fe', 'w-fe-display');
bindSlider('w-fo', 'w-fo-display');

// ── Position badge ────────────────────────────────────────────────────────
function posBadge(pos) {
  return `<span class="pos-badge ${pos}">${pos}</span>`;
}

// ── Bar chart cell ────────────────────────────────────────────────────────
function bar(value, max = 1) {
  const pct = Math.min(100, Math.round((value / max) * 100));
  return `<div class="bar"><div class="bar-fill" style="width:${pct}%"></div></div>`;
}

// ── Player card ────────────────────────────────────────────────────────────
function playerCard(p, captainId, viceCaptainId) {
  const isCap  = p.id === captainId;
  const isVC   = p.id === viceCaptainId;
  const cls    = `player-card${isCap ? ' captain' : isVC ? ' vice' : ''}`;
  const badge  = isCap ? '<span class="cap-badge">C</span>'
               : isVC  ? '<span class="cap-badge vc-badge">V</span>'
               : '';
  return `
    <div class="${cls}">
      ${badge}
      ${posBadge(p.position)}
      <div class="player-name">${p.short_name || p.name}</div>
      <div class="player-team">${p.team}</div>
      <div class="player-pts">${p.predicted_points.toFixed(1)}</div>
      <div class="player-pts-label">pred pts (3 games)</div>
      <div class="player-cost">$${p.cost.toFixed(1)}m</div>
    </div>`;
}

// ── OPTIMIZER ─────────────────────────────────────────────────────────────
document.getElementById('optimize-btn').addEventListener('click', async () => {
  const btn = document.getElementById('optimize-btn');
  const result = document.getElementById('squad-result');
  const loading = document.getElementById('optimizer-loading');
  const errorEl = document.getElementById('optimizer-error');

  btn.disabled = true;
  result.classList.add('hidden');
  errorEl.classList.add('hidden');
  loading.classList.remove('hidden');

  try {
    const payload = {
      budget:          parseInt(document.getElementById('budget').value),
      w_team_strength: parseFloat(document.getElementById('w-ts').value),
      w_fixture_ease:  parseFloat(document.getElementById('w-fe').value),
      w_form:          parseFloat(document.getElementById('w-fo').value),
      w_position_role: parseFloat((1 - parseFloat(document.getElementById('w-ts').value)
                       - parseFloat(document.getElementById('w-fe').value)
                       - parseFloat(document.getElementById('w-fo').value)).toFixed(2)),
    };

    const res = await fetch('/api/optimize', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    if (!res.ok) throw new Error(`Server error: ${res.status}`);
    const data = await res.json();

    document.getElementById('total-cost').textContent = `$${data.total_cost.toFixed(1)}m`;
    document.getElementById('total-pts').textContent  = data.total_predicted_points.toFixed(1);

    document.getElementById('starters-grid').innerHTML =
      data.starters.map(p => playerCard(p, data.captain_id, data.vice_captain_id)).join('');
    document.getElementById('bench-grid').innerHTML =
      data.bench.map(p => playerCard(p, null, null)).join('');

    result.classList.remove('hidden');
  } catch (e) {
    errorEl.textContent = `Error: ${e.message}`;
    errorEl.classList.remove('hidden');
  } finally {
    loading.classList.add('hidden');
    btn.disabled = false;
  }
});

// ── PLAYERS TABLE ─────────────────────────────────────────────────────────
let allPlayers = [];
let playersLoaded = false;

async function loadPlayers() {
  const loading = document.getElementById('players-loading');
  const errorEl = document.getElementById('players-error');
  const wrap    = document.getElementById('players-table-wrap');

  loading.classList.remove('hidden');
  wrap.classList.add('hidden');
  errorEl.classList.add('hidden');

  try {
    const res = await fetch('/api/players');
    if (!res.ok) throw new Error(`Server error: ${res.status}`);
    allPlayers = await res.json();
    playersLoaded = true;
    renderPlayers();
    wrap.classList.remove('hidden');
  } catch (e) {
    errorEl.textContent = `Error loading players: ${e.message}`;
    errorEl.classList.remove('hidden');
  } finally {
    loading.classList.add('hidden');
  }
}

function renderPlayers() {
  const search = (document.getElementById('player-search').value || '').toLowerCase();
  const pos    = document.getElementById('pos-filter').value;
  const sortBy = document.getElementById('sort-by').value;

  let players = allPlayers.filter(p =>
    (!pos || p.position === pos) &&
    (!search || p.name.toLowerCase().includes(search) || p.team.toLowerCase().includes(search))
  );

  players.sort((a, b) => b[sortBy] - a[sortBy]);

  document.getElementById('players-tbody').innerHTML = players.map(p => `
    <tr>
      <td>${p.short_name || p.name}</td>
      <td>${p.team}</td>
      <td>${posBadge(p.position)}</td>
      <td>$${p.cost.toFixed(1)}m</td>
      <td><strong>${p.predicted_points.toFixed(1)}</strong></td>
      <td>${bar(p.team_strength)} ${(p.team_strength * 100).toFixed(0)}%</td>
      <td>${bar(p.fixture_ease)} ${(p.fixture_ease * 100).toFixed(0)}%</td>
      <td>${bar(p.form_score)} ${(p.form_score * 100).toFixed(0)}%</td>
      <td>${p.total_points}</td>
      <td>${p.picked_by.toFixed(1)}%</td>
    </tr>`).join('');
}

['player-search', 'pos-filter', 'sort-by'].forEach(id =>
  document.getElementById(id).addEventListener('input', renderPlayers)
);

// ── FIXTURES ─────────────────────────────────────────────────────────────
let fixturesLoaded = false;

async function loadFixtures() {
  const loading = document.getElementById('fixtures-loading');
  const errorEl = document.getElementById('fixtures-error');
  const content = document.getElementById('fixtures-content');

  loading.classList.remove('hidden');
  content.classList.add('hidden');
  errorEl.classList.add('hidden');

  try {
    const res = await fetch('/api/fixtures');
    if (!res.ok) throw new Error(`Server error: ${res.status}`);
    const rounds = await res.json();
    fixturesLoaded = true;

    content.innerHTML = rounds.map(rnd => `
      <div class="round-card">
        <div class="round-header">
          <h3>Round ${rnd.id} – ${rnd.stage.charAt(0).toUpperCase() + rnd.stage.slice(1)}</h3>
          <span class="round-status">${rnd.status}</span>
        </div>
        ${rnd.fixtures.map(f => `
          <div class="fixture-row">
            <span class="team-name">${f.home_team}</span>
            <span class="score">${f.home_score != null ? `${f.home_score} – ${f.away_score}` : 'vs'}</span>
            <span class="team-name away">${f.away_team}</span>
            <span class="fixture-date">${f.date ? new Date(f.date).toLocaleDateString('en-GB', {day:'numeric',month:'short',hour:'2-digit',minute:'2-digit'}) : ''}</span>
          </div>`).join('')}
      </div>`).join('');

    content.classList.remove('hidden');
  } catch (e) {
    errorEl.textContent = `Error loading fixtures: ${e.message}`;
    errorEl.classList.remove('hidden');
  } finally {
    loading.classList.add('hidden');
  }
}
