// Swipe interface for discover page
const stack = document.getElementById('swipeStack');
if (!stack) { /* not on discover page */ }
else {
  let cards = Array.from(stack.querySelectorAll('.swipe-card'));
  let current = cards[cards.length - 1]; // top card
  let startX = 0, startY = 0, isDragging = false;

  function getTopCard() {
    const all = stack.querySelectorAll('.swipe-card:not(.fly-left):not(.fly-right)');
    return all[all.length - 1] || null;
  }

  function sendSwipe(chairId, action) {
    return fetch('/swipe', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ chair_id: parseInt(chairId), action })
    }).then(r => r.json());
  }

  function animateCard(card, direction) {
    card.classList.add(direction === 'like' ? 'fly-right' : 'fly-left');
    setTimeout(() => card.remove(), 350);
  }

  function showMatchOverlay(compat, chairCode) {
    if (compat >= 85) {
      const overlay = document.getElementById('matchOverlay');
      document.getElementById('matchMsg').textContent =
        `Chair ${chairCode} has a lot in common with you. ${compat}% compatibility!`;
      overlay.classList.add('show');
      setTimeout(() => overlay.classList.remove('show'), 3500);
    }
  }

  window.doSwipe = function(action) {
    const card = getTopCard();
    if (!card) return;
    const chairId = card.dataset.chairId;
    const compat = parseInt(card.dataset.compat);
    const code = card.querySelector('.chair-code').textContent.trim();
    animateCard(card, action);
    sendSwipe(chairId, action).then(data => {
      if (action === 'like') showMatchOverlay(compat, code);
      if (data.achievements && data.achievements.length) {
        data.achievements.forEach(a => showToast('🏅 Achievement unlocked: ' + a, 'var(--warning)'));
      }
    });
  };

  // Touch/mouse drag
  function onStart(e) {
    const card = getTopCard();
    if (!card) return;
    isDragging = true;
    card.classList.add('swiping');
    const pt = e.touches ? e.touches[0] : e;
    startX = pt.clientX; startY = pt.clientY;
  }

  function onMove(e) {
    if (!isDragging) return;
    const card = getTopCard();
    if (!card) return;
    const pt = e.touches ? e.touches[0] : e;
    const dx = pt.clientX - startX;
    const dy = pt.clientY - startY;
    const rot = dx * 0.08;
    card.style.transform = `translateX(${dx}px) translateY(${dy}px) rotate(${rot}deg)`;
    card.style.opacity = 1 - Math.abs(dx) / 400;
  }

  function onEnd(e) {
    if (!isDragging) return;
    isDragging = false;
    const card = getTopCard();
    if (!card) return;
    card.classList.remove('swiping');
    const pt = e.changedTouches ? e.changedTouches[0] : e;
    const dx = pt.clientX - startX;
    if (dx > 80) doSwipe('like');
    else if (dx < -80) doSwipe('dislike');
    else { card.style.transform = ''; card.style.opacity = ''; }
  }

  stack.addEventListener('mousedown', onStart);
  document.addEventListener('mousemove', onMove);
  document.addEventListener('mouseup', onEnd);
  stack.addEventListener('touchstart', onStart, { passive: true });
  document.addEventListener('touchmove', onMove, { passive: true });
  document.addEventListener('touchend', onEnd);
}
