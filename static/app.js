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

// ── Slider labels (removed — model is now fully ELO/price-driven) ──────────

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

  const predGame = [null, p.predicted_g1, p.predicted_g2, p.predicted_g3];
  const rs   = p.round_scores    || {};
  const ro   = p.round_opponents || {};
  const rd   = p.round_dates     || {};
  const rdr  = p.round_day_ranks || {};
  const rdc  = p.round_day_count || {};
  let totalDisplay = 0;
  const gameRows = [1, 2, 3].map(r => {
    const actual  = rs[r] != null ? rs[r] : null;
    const pred    = predGame[r] != null ? predGame[r] : (p.predicted_points / 3);
    const opp     = shortTeam(ro[r] || '');
    const dayRank  = rdr[r];
    const dayCount = rdc[r];
    const dateStr  = rd[r]
      ? `${shortDate(rd[r])}${dayRank ? ` D${dayRank}/${dayCount}` : ''}`
      : '';
    if (actual !== null) {
      totalDisplay += actual;
      return `<div class="game-row actual"><span class="game-label">G${r}</span><span class="game-opp">${opp}</span><span class="game-date">${dateStr}</span><span class="game-score">${actual} pts</span></div>`;
    } else {
      totalDisplay += pred;
      return `<div class="game-row predicted"><span class="game-label">G${r}</span><span class="game-opp">${opp}</span><span class="game-date">${dateStr}</span><span class="game-score">~${pred.toFixed(1)}</span></div>`;
    }
  }).join('');

  const anyActual = [1,2,3].some(r => rs[r] != null);
  const totalLabel = anyActual ? 'Total' : 'Pred Total';

  return `
    <div class="${cls}">
      ${badge}
      <div class="card-top">
        ${posBadge(p.position)}
        <div class="player-name">${p.short_name || p.name}</div>
        <div class="player-team">${p.team}</div>
      </div>
      <div class="game-breakdown">${gameRows}</div>
      <div class="card-total">
        <span class="total-label">${totalLabel}</span>
        <span class="total-pts">${totalDisplay.toFixed(1)}</span>
      </div>
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
      budget: Math.round(parseFloat(document.getElementById('budget').value) * 10),
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

    const byPos = { GKP: [], DEF: [], MID: [], FWD: [] };
    data.starters.forEach(p => (byPos[p.position] || (byPos[p.position] = [])).push(p));
    ['GKP','DEF','MID','FWD'].forEach(pos => {
      document.getElementById('row-' + pos.toLowerCase()).innerHTML =
        (byPos[pos] || []).map(p => playerCard(p, data.captain_id, data.vice_captain_id)).join('');
    });
    document.getElementById('bench-grid').innerHTML =
      data.bench.map(p => playerCard(p, null, null)).join('');

    // Show any unresolved same-day conflicts
    const conflictEl = document.getElementById('optimizer-conflicts');
    if (data.conflicts && data.conflicts.length > 0) {
      conflictEl.innerHTML = data.conflicts.map(c => `<div>${c}</div>`).join('');
      conflictEl.classList.remove('hidden');
    } else {
      conflictEl.classList.add('hidden');
    }

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

let sortCol = 'predicted_points';
let sortDir = 'desc';

function renderPlayers() {
  const search = (document.getElementById('player-search').value || '').toLowerCase();
  const pos    = document.getElementById('pos-filter').value;

  let players = allPlayers.filter(p =>
    (!pos || p.position === pos) &&
    (!search || p.name.toLowerCase().includes(search) || p.team.toLowerCase().includes(search))
  );

  const isStr = document.querySelector(`th[data-col="${sortCol}"]`)?.dataset.type === 'str';
  players.sort((a, b) => {
    const av = a[sortCol], bv = b[sortCol];
    const cmp = isStr ? String(av).localeCompare(String(bv)) : (av - bv);
    return sortDir === 'asc' ? cmp : -cmp;
  });

  // Update header arrows
  document.querySelectorAll('#players-table thead th').forEach(th => {
    const arrow = th.dataset.col === sortCol ? (sortDir === 'asc' ? ' ▲' : ' ▼') : ' ⇅';
    th.textContent = th.textContent.replace(/ [▲▼⇅]$/, '') + arrow;
  });

  const predGame = (p, r) => [null, p.predicted_g1, p.predicted_g2, p.predicted_g3][r] ?? (p.predicted_points / 3);
  const gameCell = (p, r) => {
    const rs = p.round_scores || {};
    const actual = rs[r] != null ? rs[r] : null;
    if (actual !== null)
      return `<td class="game-actual">${actual}</td>`;
    return `<td class="game-pred">~${predGame(p, r).toFixed(1)}</td>`;
  };

  // attach virtual g1/g2/g3 for sorting
  players.forEach(p => {
    const rs = p.round_scores || {};
    p.g1 = rs[1] != null ? rs[1] : predGame(p, 1);
    p.g2 = rs[2] != null ? rs[2] : predGame(p, 2);
    p.g3 = rs[3] != null ? rs[3] : predGame(p, 3);
  });

  document.getElementById('players-tbody').innerHTML = players.map(p => `
    <tr>
      <td>${p.short_name || p.name}</td>
      <td>${p.team}</td>
      <td>${posBadge(p.position)}</td>
      <td>$${p.cost.toFixed(1)}m</td>
      <td><strong>${p.predicted_points.toFixed(1)}</strong></td>
      ${gameCell(p, 1)}${gameCell(p, 2)}${gameCell(p, 3)}
      <td>${bar(p.team_strength)} ${(p.team_strength * 100).toFixed(0)}%</td>
      <td>${bar(p.fixture_ease)} ${(p.fixture_ease * 100).toFixed(0)}%</td>
      <td>${bar(p.form_score)} ${(p.form_score * 100).toFixed(0)}%</td>
      <td>${p.total_points}</td>
      <td>${p.picked_by.toFixed(1)}%</td>
    </tr>`).join('');
}

['player-search', 'pos-filter'].forEach(id =>
  document.getElementById(id).addEventListener('input', renderPlayers)
);

document.querySelectorAll('#players-table thead th[data-col]').forEach(th => {
  th.style.cursor = 'pointer';
  th.addEventListener('click', () => {
    if (sortCol === th.dataset.col) {
      sortDir = sortDir === 'asc' ? 'desc' : 'asc';
    } else {
      sortCol = th.dataset.col;
      sortDir = th.dataset.type === 'str' ? 'asc' : 'desc';
    }
    renderPlayers();
  });
});

// ── FIXTURES (groups A–L) ────────────────────────────────────────────────
let fixturesLoaded = false;

const SHORT_NAMES = {
  'Korea Republic':         'Korea',
  'Bosnia and Herzegovina': 'Bosnia',
  'Côte d\'Ivoire':         'C. d\'Ivoire',
  'New Zealand':            'New Zealand',
  'Saudi Arabia':           'Saudi Arabia',
  'South Africa':           'South Africa',
  'United Arab Emirates':   'UAE',
  'North Macedonia':        'N. Macedonia',
  'Congo DR':               'Congo DR',
  'IR Iran':                'Iran',
};
function shortTeam(name) { return SHORT_NAMES[name] || name; }

function shortDate(iso) {
  // "2026-06-14" → "Jun 14"
  if (!iso) return '';
  const [, m, d] = iso.split('-');
  const months = ['','Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
  return `${months[parseInt(m)]} ${parseInt(d)}`;
}

function fmtDate(iso) {
  if (!iso) return '';
  const d = new Date(iso);
  return d.toLocaleDateString('en-GB', { day: 'numeric', month: 'short' })
    + ' ' + d.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' });
}

function strengthBar(strength) {
  const pct = Math.round(strength * 100);
  return `<div class="str-bar"><div class="str-fill" style="width:${pct}%"></div></div>`;
}

async function loadFixtures() {
  const loading = document.getElementById('fixtures-loading');
  const errorEl = document.getElementById('fixtures-error');
  const content = document.getElementById('fixtures-content');

  loading.classList.remove('hidden');
  content.classList.add('hidden');
  errorEl.classList.add('hidden');

  try {
    const res = await fetch('/api/groups');
    if (!res.ok) throw new Error(`Server error: ${res.status}`);
    const groups = await res.json();
    fixturesLoaded = true;

    content.innerHTML = `<div class="groups-grid">` + groups.map(g => `
      <div class="group-card">
        <div class="group-header">Group ${g.name}</div>
        <div class="group-body">
          <div class="group-teams">
            <table class="teams-table">
              <thead><tr><th>Team</th><th>Elo</th><th>Strength</th></tr></thead>
              <tbody>
                ${g.teams.sort((a,b) => b.rank - a.rank).map(t => `
                  <tr>
                    <td><span class="team-abbr">${t.abbr}</span> ${shortTeam(t.name)}</td>
                    <td class="rank-cell">${t.rank}</td>
                    <td>${strengthBar(t.strength)} ${Math.round(t.strength*100)}%</td>
                  </tr>`).join('')}
              </tbody>
            </table>
          </div>
          <div class="group-fixtures">
            ${g.fixtures.map(f => `
              <div class="gf-row">
                <span class="gf-game">G${f.game}</span>
                <span class="gf-home">${shortTeam(f.home_team)}</span>
                <span class="gf-score">${f.home_score != null ? `${f.home_score}–${f.away_score}` : 'vs'}</span>
                <span class="gf-away">${shortTeam(f.away_team)}</span>
                <span class="gf-date">${fmtDate(f.date)}</span>
              </div>`).join('')}
          </div>
        </div>
      </div>`).join('') + `</div>`;

    content.classList.remove('hidden');
  } catch (e) {
    errorEl.textContent = `Error loading fixtures: ${e.message}`;
    errorEl.classList.remove('hidden');
  } finally {
    loading.classList.add('hidden');
  }
}
