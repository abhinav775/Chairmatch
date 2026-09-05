const card = document.getElementById('topCard');
if (!card) { /* not on discover page */ }
else {
  let idx = 0; // index into CHAIRS array (next cards)
  let isDragging = false, startX = 0, startY = 0;

  function sendSwipe(chairId, action) {
    return fetch('/swipe', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ chair_id: parseInt(chairId), action })
    }).then(r => r.json());
  }

  function loadNextCard() {
    if (idx >= CHAIRS.length) {
      card.innerHTML = `<div style="text-align:center;padding:3rem 1rem;">
        <div style="font-size:3rem;">💔</div>
        <h2 style="margin:1rem 0;">You've seen all the chairs.</h2>
        <p style="color:var(--text2);">Every chair has found someone. Tough luck.</p>
        <a href="/classroom" class="btn btn-primary" style="margin-top:1rem;display:inline-flex;">View Classroom Map</a>
      </div>`;
      card.style.transform = '';
      card.style.opacity = '';
      document.getElementById('remainCount') && (document.getElementById('remainCount').textContent = '0');
      return;
    }
    const c = CHAIRS[idx];
    const compat = COMPATS[idx];
    const bd = BREAKDOWNS[idx];
    idx++;

    const tags = [];
    if (c.row >= 5) tags.push('🦥 Back Row');
    if (c.row <= 2) tags.push('👑 Front Row');
    if (c.window_score >= 7) tags.push('🪟 Window Seat');
    if (c.charging) tags.push('⚡ Charging');

    card.dataset.chairId = c.id;
    card.dataset.compat = compat;
    card.innerHTML = `
      <div class="chair-emoji">💺</div>
      <div class="chair-code">${c.chair_code}</div>
      <div class="chair-location">${c.classroom_name} · Row ${c.row}</div>
      <div class="compat-big">${compat}%</div>
      <div class="compat-label">COMPATIBILITY MATCH</div>
      <div class="breakdown-grid">
        <div class="breakdown-item"><div class="bi-label">🪟 Window</div><div class="bi-val">${Math.round(bd.window)}%</div></div>
        <div class="breakdown-item"><div class="bi-label">👀 Board Visibility</div><div class="bi-val">${Math.round(bd.visibility)}%</div></div>
        <div class="breakdown-item"><div class="bi-label">⚡ Charging</div><div class="bi-val">${Math.round(bd.charging)}%</div></div>
        <div class="breakdown-item"><div class="bi-label">🪑 Row Position</div><div class="bi-val">${Math.round(bd.front_back)}%</div></div>
      </div>
      <div class="chair-tags">${tags.map(t => `<span class="chair-tag">${t}</span>`).join('')}</div>
      <div class="card-actions">
        <button class="btn-nope" onclick="doSwipe('dislike')">👎 NOPE</button>
        <a href="/chair/${c.id}" class="btn btn-details">Details</a>
        <button class="btn-like" onclick="doSwipe('like')">❤️ LIKE</button>
      </div>`;
    card.style.transform = '';
    card.style.opacity = '';
    card.classList.remove('fly-left', 'fly-right');
    const rem = document.getElementById('remainCount');
    if (rem) rem.textContent = CHAIRS.length - idx + 1;
  }

  window.doSwipe = function(action) {
    const chairId = card.dataset.chairId;
    const compat = parseInt(card.dataset.compat);
    const code = card.querySelector('.chair-code') ? card.querySelector('.chair-code').textContent.trim() : '';

    card.classList.add(action === 'like' ? 'fly-right' : 'fly-left');
    setTimeout(loadNextCard, 320);

    sendSwipe(chairId, action).then(data => {
      if (data.achievements && data.achievements.length) {
        data.achievements.forEach(a => showToast('🏅 Achievement: ' + a, 'var(--warning)'));
      }
    });
  };

  // Drag to swipe
  card.addEventListener('mousedown', e => {
    if (e.target.tagName === 'BUTTON' || e.target.tagName === 'A') return;
    isDragging = true; card.classList.add('swiping');
    startX = e.clientX; startY = e.clientY;
  });
  document.addEventListener('mousemove', e => {
    if (!isDragging) return;
    const dx = e.clientX - startX, dy = e.clientY - startY;
    card.style.transform = `translateX(${dx}px) translateY(${dy}px) rotate(${dx * 0.07}deg)`;
    card.style.opacity = String(1 - Math.abs(dx) / 400);
  });
  document.addEventListener('mouseup', e => {
    if (!isDragging) return;
    isDragging = false; card.classList.remove('swiping');
    const dx = e.clientX - startX;
    if (dx > 80) doSwipe('like');
    else if (dx < -80) doSwipe('dislike');
    else { card.style.transform = ''; card.style.opacity = ''; }
  });
  card.addEventListener('touchstart', e => {
    if (e.target.tagName === 'BUTTON' || e.target.tagName === 'A') return;
    isDragging = true; card.classList.add('swiping');
    startX = e.touches[0].clientX; startY = e.touches[0].clientY;
  }, { passive: true });
  document.addEventListener('touchmove', e => {
    if (!isDragging) return;
    const dx = e.touches[0].clientX - startX, dy = e.touches[0].clientY - startY;
    card.style.transform = `translateX(${dx}px) translateY(${dy}px) rotate(${dx * 0.07}deg)`;
    card.style.opacity = String(1 - Math.abs(dx) / 400);
  }, { passive: true });
  document.addEventListener('touchend', e => {
    if (!isDragging) return;
    isDragging = false; card.classList.remove('swiping');
    const dx = e.changedTouches[0].clientX - startX;
    if (dx > 80) doSwipe('like');
    else if (dx < -80) doSwipe('dislike');
    else { card.style.transform = ''; card.style.opacity = ''; }
  });
}
