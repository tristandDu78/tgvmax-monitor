'use strict';

/* ─── helpers ─────────────────────────────────────────────────── */
const $ = (id) => document.getElementById(id);
const qs = (sel, ctx = document) => ctx.querySelector(sel);

let _toastTimer;
function toast(msg, type = '') {
  const el = $('toast');
  el.textContent = msg;
  el.className = 'show ' + type;
  clearTimeout(_toastTimer);
  _toastTimer = setTimeout(() => { el.className = ''; }, 3200);
}

async function apiFetch(method, path, body) {
  const r = await fetch(path, {
    method,
    headers: { 'Content-Type': 'application/json' },
    body: body ? JSON.stringify(body) : undefined,
  });
  let data = {};
  try { data = await r.json(); } catch (_) {}
  if (!r.ok) throw new Error(data.detail || `Erreur ${r.status}`);
  return data;
}

/* ─── sélecteurs horaires ─────────────────────────────────────── */
function fillTimeSelects() {
  const from = $('f-from');
  const to   = $('f-to');
  if (!from || !to) return;

  const frag1 = document.createDocumentFragment();
  const frag2 = document.createDocumentFragment();

  for (let h = 0; h < 24; h++) {
    for (const m of [0, 30]) {
      const v = String(h).padStart(2, '0') + ':' + String(m).padStart(2, '0');
      const o1 = document.createElement('option');
      o1.value = o1.textContent = v;
      const o2 = document.createElement('option');
      o2.value = o2.textContent = v;
      frag1.appendChild(o1);
      frag2.appendChild(o2);
    }
  }

  from.appendChild(frag1);
  to.appendChild(frag2);
  from.value = '06:00';
  to.value   = '20:00';
}

/* ─── date min / max ──────────────────────────────────────────── */
function initDate() {
  const inp  = $('f-date');
  if (!inp) return;
  const pad  = (n) => String(n).padStart(2, '0');
  const fmt  = (d) => `${d.getFullYear()}-${pad(d.getMonth()+1)}-${pad(d.getDate())}`;
  const today = new Date();
  const max   = new Date(today); max.setDate(max.getDate() + 30);
  inp.min   = fmt(today);
  inp.max   = fmt(max);
  inp.value = fmt(today);
}

/* ─── autocomplete ────────────────────────────────────────────── */
function autocomplete(inputId, listId) {
  const inp  = $(inputId);
  const list = $(listId);
  if (!inp || !list) return;
  let timer;

  inp.addEventListener('input', () => {
    clearTimeout(timer);
    const q = inp.value.trim();
    if (q.length < 2) { list.className = 'ac-list'; return; }
    timer = setTimeout(() => loadGares(q, inp, list), 250);
  });

  inp.addEventListener('blur', () => {
    setTimeout(() => { list.className = 'ac-list'; }, 200);
  });

  inp.addEventListener('keydown', (e) => {
    const items  = [...list.querySelectorAll('.ac-item')];
    const active = list.querySelector('.hi');
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      const next = active ? active.nextElementSibling : items[0];
      active?.classList.remove('hi'); next?.classList.add('hi');
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      const prev = active?.previousElementSibling;
      active?.classList.remove('hi'); prev?.classList.add('hi');
    } else if (e.key === 'Enter' && active) {
      e.preventDefault();
      inp.value = active.dataset.v;
      list.className = 'ac-list';
    } else if (e.key === 'Escape') {
      list.className = 'ac-list';
    }
  });
}

async function loadGares(q, inp, list) {
  try {
    const gares = await apiFetch('GET', `/api/gares?q=${encodeURIComponent(q)}`);
    list.innerHTML = '';
    if (!gares.length) { list.className = 'ac-list'; return; }
    const frag = document.createDocumentFragment();
    gares.forEach((g) => {
      const div = document.createElement('div');
      div.className   = 'ac-item';
      div.dataset.v   = g;
      const idx = g.toUpperCase().indexOf(q.toUpperCase());
      div.innerHTML   = idx >= 0
        ? g.slice(0, idx) + '<mark>' + g.slice(idx, idx + q.length) + '</mark>' + g.slice(idx + q.length)
        : g;
      div.addEventListener('mousedown', () => {
        inp.value = g;
        list.className = 'ac-list';
      });
      frag.appendChild(div);
    });
    list.appendChild(frag);
    list.className = 'ac-list open';
  } catch (_) {
    list.className = 'ac-list';
  }
}

/* ─── affichage des surveillances ─────────────────────────────── */
function fmtDate(iso) {
  if (!iso) return '';
  const [y, m, d] = iso.split('-');
  return `${d}/${m}/${y}`;
}

function renderWatches(list) {
  const wrap = $('watches-list');
  if (!list.length) {
    wrap.innerHTML = `
      <div class="empty-state">
        <div class="ei">🔍</div>
        Aucune surveillance active.<br>Utilisez le formulaire ci-dessus pour en créer une.
      </div>`;
    return;
  }
  wrap.innerHTML = list.map((w) => {
    const trains = Array.isArray(w.last_check_trains) ? w.last_check_trains : [];
    const trainsHtml = trains.length
      ? trains.map((t) =>
          `<div class="train-row">
            🚆 <span class="t-num">Train ${t.train_no}</span>
            <span class="t-time">${t.departure} → ${t.arrival}</span>
          </div>`).join('')
      : `<div class="no-trains">Aucune place disponible au dernier contrôle</div>`;

    return `<div class="watch-card">
      <div class="wc-head">
        <div>
          <div class="wc-route">${w.origin}<span class="wc-arrow">→</span>${w.destination}</div>
          <div class="wc-meta">
            <span class="pill">📅 ${fmtDate(w.travel_date)}</span>
            <span class="pill">🕐 ${(w.time_from||'').slice(0,5)} – ${(w.time_to||'').slice(0,5)}</span>
          </div>
        </div>
        <button class="btn-del" data-id="${w.id}">Supprimer</button>
      </div>
      <div class="trains">${trainsHtml}</div>
    </div>`;
  }).join('');

  wrap.querySelectorAll('.btn-del').forEach((btn) => {
    btn.addEventListener('click', () => deleteWatch(btn.dataset.id));
  });
}

async function loadWatches() {
  try {
    const list = await apiFetch('GET', '/api/watches');
    renderWatches(list);
  } catch (_) {
    $('watches-list').innerHTML =
      `<div class="empty-state" style="color:var(--red)">Impossible de charger les surveillances.</div>`;
  }
}

async function deleteWatch(id) {
  if (!confirm('Supprimer cette surveillance ?')) return;
  try {
    await apiFetch('DELETE', `/api/watches/${id}`);
    toast('Surveillance supprimée.', 'ok');
    loadWatches();
  } catch (e) {
    toast(e.message, 'err');
  }
}

/* ─── soumission ──────────────────────────────────────────────── */
async function onSubmit(e) {
  e.preventDefault();
  const tFrom = $('f-from').value;
  const tTo   = $('f-to').value;

  if (tFrom >= tTo) {
    toast("L'heure de début doit être avant l'heure de fin.", 'err');
    return;
  }

  const body = {
    origin:      $('f-origin').value.trim().toUpperCase(),
    destination: $('f-dest').value.trim().toUpperCase(),
    travel_date: $('f-date').value,
    time_from:   tFrom,
    time_to:     tTo,
  };

  if (!body.origin || !body.destination) {
    toast('Veuillez renseigner les gares de départ et d\'arrivée.', 'err');
    return;
  }

  const btn = $('btn-submit');
  btn.disabled = true;
  btn.innerHTML = '<span class="spin"></span> Enregistrement…';

  try {
    await apiFetch('POST', '/api/watches', body);
    toast('✅ Surveillance créée ! Vous recevrez un DM Discord dès qu\'une place est dispo.', 'ok');
    e.target.reset();
    initDate();
    $('f-from').value = '06:00';
    $('f-to').value   = '20:00';
    loadWatches();
  } catch (err) {
    toast(err.message, 'err');
  } finally {
    btn.disabled = false;
    btn.textContent = '🔔 Surveiller ce trajet';
  }
}

/* ─── état auth ───────────────────────────────────────────────── */
function setAuth(ok, user) {
  $('hdr-login').style.display    = ok ? 'none'  : '';
  $('hdr-user').style.display     = ok ? 'flex'  : 'none';
  $('login-banner').style.display = ok ? 'none'  : '';
  $('features').style.display     = ok ? 'none'  : '';
  $('watches-wrap').style.display = ok ? 'block' : 'none';
  $('btn-submit').disabled        = !ok;

  if (!ok) {
    $('btn-submit').textContent = '🔒 Connectez-vous pour surveiller';
    return;
  }
  $('btn-submit').textContent = '🔔 Surveiller ce trajet';

  // Avatar
  const wrap = $('u-avatar');
  wrap.innerHTML = '';
  if (user.avatar) {
    const img = document.createElement('img');
    img.src       = `https://cdn.discordapp.com/avatars/${user.discord_id}/${user.avatar}.png?size=64`;
    img.alt       = user.username;
    img.className = 'user-avatar';
    wrap.appendChild(img);
  } else {
    const fb = document.createElement('div');
    fb.className  = 'user-avatar-fb';
    fb.textContent = (user.username || '?')[0].toUpperCase();
    wrap.appendChild(fb);
  }
  $('u-name').textContent = user.username;
  loadWatches();
}

/* ─── erreur URL ──────────────────────────────────────────────── */
function checkOAuthError() {
  const p = new URLSearchParams(location.search);
  const e = p.get('error');
  if (!e) return;
  const msgs = {
    access_denied:        'Connexion annulée.',
    invalid_state:        'Erreur de sécurité. Réessayez.',
    token_exchange_failed:'Échec de connexion Discord. Réessayez.',
  };
  const el = $('err-banner');
  el.textContent = msgs[e] || `Erreur : ${e}`;
  el.classList.add('on');
  history.replaceState({}, '', '/');
}

/* ─── init ────────────────────────────────────────────────────── */
async function init() {
  checkOAuthError();

  /* Remplir les selects IMMÉDIATEMENT, avant tout appel réseau */
  fillTimeSelects();
  initDate();

  autocomplete('f-origin', 'ac-origin');
  autocomplete('f-dest',   'ac-dest');
  $('watch-form').addEventListener('submit', onSubmit);

  /* Vérifier la session */
  try {
    const { authenticated, user } = await apiFetch('GET', '/api/me');
    setAuth(authenticated, user || {});
  } catch (_) {
    setAuth(false, {});
  }
}

document.addEventListener('DOMContentLoaded', init);
