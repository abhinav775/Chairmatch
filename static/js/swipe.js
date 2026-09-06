const card = document.getElementById('topCard');

if (!card) {
  /* not on discover page */
}
else {

  let idx = 0; // index into CHAIRS array (next cards)
  let isDragging = false, startX = 0, startY = 0;
  let swipeInProgress = false;


  function sendSwipe(chairId, action) {
    return fetch('/swipe', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        chair_id: parseInt(chairId),
        action: action
      })
    }).then(r => {
      if (!r.ok) {
        throw new Error('Swipe request failed');
      }
      return r.json();
    });
  }


  function loadNextCard() {

    if (idx >= CHAIRS.length) {

      card.innerHTML = `
        <div style="text-align:center;padding:3rem 1rem;">
          <div style="font-size:3rem;">💔</div>

          <h2 style="margin:1rem 0;">
            You've seen all the chairs.
          </h2>

          <p style="color:var(--text2);">
            Every chair has found someone. Tough luck.
          </p>

          <a
            href="/classroom"
            class="btn btn-primary"
            style="margin-top:1rem;display:inline-flex;"
          >
            View Classroom Map
          </a>
        </div>
      `;

      card.style.transform = '';
      card.style.opacity = '';

      const remain = document.getElementById('remainCount');

      if (remain) {
        remain.textContent = '0';
      }

      return;
    }


    const c = CHAIRS[idx];
    const compat = COMPATS[idx];
    const bd = BREAKDOWNS[idx];

    idx++;


    const tags = [];

    if (c.row >= 5) {
      tags.push('🦥 Back Row');
    }

    if (c.row <= 2) {
      tags.push('👑 Front Row');
    }

    if (c.window_score >= 7) {
      tags.push('🪟 Window Seat');
    }

    if (c.charging) {
      tags.push('⚡ Charging');
    }


    card.dataset.chairId = c.id;
    card.dataset.compat = compat;


    card.innerHTML = `
      <div class="chair-emoji">💺</div>

      <div class="chair-code">
        ${c.chair_code}
      </div>

      <div class="chair-location">
        ${c.classroom_name} · Row ${c.row}
      </div>

      <div class="compat-big">
        ${compat}%
      </div>

      <div class="compat-label">
        COMPATIBILITY MATCH
      </div>

      <div class="breakdown-grid">

        <div class="breakdown-item">
          <div class="bi-label">🪟 Window</div>
          <div class="bi-val">
            ${Math.round(bd.window)}%
          </div>
        </div>

        <div class="breakdown-item">
          <div class="bi-label">👀 Board Visibility</div>
          <div class="bi-val">
            ${Math.round(bd.visibility)}%
          </div>
        </div>

        <div class="breakdown-item">
          <div class="bi-label">⚡ Charging</div>
          <div class="bi-val">
            ${Math.round(bd.charging)}%
          </div>
        </div>

        <div class="breakdown-item">
          <div class="bi-label">🪑 Row Position</div>
          <div class="bi-val">
            ${Math.round(bd.front_back)}%
          </div>
        </div>

      </div>

      <div class="chair-tags">
        ${tags.map(t => `<span class="chair-tag">${t}</span>`).join('')}
      </div>

      <div class="card-actions">

        <button
          class="btn-nope"
          onclick="doSwipe('dislike')"
        >
          👎 NOPE
        </button>

        <a
          href="/chair/${c.id}"
          class="btn btn-details"
        >
          Details
        </a>

        <button
          class="btn-like"
          onclick="doSwipe('like')"
        >
          ❤️ LIKE
        </button>

      </div>
    `;


    card.style.transform = '';
    card.style.opacity = '';

    card.classList.remove('fly-left', 'fly-right');


    const rem = document.getElementById('remainCount');

    if (rem) {
      rem.textContent = CHAIRS.length - idx + 1;
    }
  }



  /*
   * LIKE / DISLIKE
   */
  window.doSwipe = function(action) {

    // Prevent accidental double-clicks / double swipes
    if (swipeInProgress) {
      return;
    }

    const chairId = card.dataset.chairId;

    if (!chairId) {
      return;
    }

    const compat = parseInt(card.dataset.compat) || 0;

    const codeElement = card.querySelector('.chair-code');

    const code = codeElement
      ? codeElement.textContent.trim()
      : '';


    swipeInProgress = true;


    // Existing swipe animation
    card.classList.add(
      action === 'like'
        ? 'fly-right'
        : 'fly-left'
    );


    /*
     * Send swipe to backend first.
     *
     * The Match popup will ONLY appear
     * if the backend successfully accepts
     * the LIKE.
     */
    sendSwipe(chairId, action)

      .then(data => {

        /*
         * Existing achievements feature
         * remains unchanged.
         */
        if (
          data.achievements &&
          data.achievements.length
        ) {

          data.achievements.forEach(a => {

            showToast(
              '🏅 Achievement: ' + a,
              'var(--warning)'
            );

          });

        }


        /*
         * NEW FEATURE:
         *
         * When the user likes a chair,
         * show the Match popup.
         */
        if (action === 'like') {

          showMatchPopup(
            chairId,
            code,
            compat
          );

        }

      })

      .catch(error => {

        console.error(
          'Swipe error:',
          error
        );

        /*
         * If the backend failed,
         * don't pretend it was a match.
         */
        showToast(
          '❌ Could not save your swipe. Please try again.',
          'var(--danger)'
        );

        // Reset card instead of losing it
        card.classList.remove(
          'fly-left',
          'fly-right'
        );

        card.style.transform = '';
        card.style.opacity = '';

        swipeInProgress = false;

      });


    /*
     * Keep your existing behavior:
     * load the next card after animation.
     */
    setTimeout(() => {

      loadNextCard();

      swipeInProgress = false;

    }, 320);

  };



  /*
   * MATCH POPUP
   */
  function showMatchPopup(chairId, code, compat) {

    // Remove an old popup if one somehow exists
    const existing =
      document.getElementById('matchPopup');

    if (existing) {
      existing.remove();
    }


    const popup =
      document.createElement('div');

    popup.id = 'matchPopup';


    popup.innerHTML = `

      <div style="
        position:fixed;
        inset:0;
        background:rgba(0,0,0,0.75);
        display:flex;
        align-items:center;
        justify-content:center;
        z-index:9999;
        padding:20px;
      ">

        <div style="
          background:var(--card);
          border:1px solid var(--border);
          border-radius:24px;
          padding:2rem;
          max-width:380px;
          width:100%;
          text-align:center;
          box-shadow:0 25px 80px rgba(0,0,0,0.5);
        ">

          <div style="
            font-size:4rem;
            margin-bottom:0.5rem;
          ">
            💘
          </div>


          <h2 style="
            margin-bottom:0.5rem;
          ">
            It's a Match!
          </h2>


          <p style="
            color:var(--text2);
            margin-bottom:0.5rem;
          ">
            You matched with chair
            <strong>${code}</strong>
          </p>


          <div style="
            font-size:1.5rem;
            font-weight:800;
            margin:0.75rem 0;
          ">
            ${compat}% Compatibility
          </div>


          <p style="
            color:var(--text2);
            font-size:0.9rem;
            margin-bottom:1.5rem;
          ">
            This chair is available.
            Would you like to reserve it?
          </p>


          <button
            onclick="reserveMatchedChair(${chairId})"
            style="
              width:100%;
              border:none;
              background:var(--primary);
              color:white;
              padding:0.9rem;
              border-radius:12px;
              font-size:1rem;
              font-weight:700;
              cursor:pointer;
              margin-bottom:0.7rem;
            "
          >
            💺 Reserve This Seat
          </button>


          <button
            onclick="closeMatchPopup()"
            style="
              width:100%;
              border:1px solid var(--border);
              background:var(--bg2);
              color:var(--text2);
              padding:0.75rem;
              border-radius:12px;
              cursor:pointer;
            "
          >
            Maybe Later
          </button>

        </div>

      </div>
    `;


    document.body.appendChild(popup);
  }



  /*
   * RESERVE MATCHED CHAIR
   */
  window.reserveMatchedChair = function(chairId) {

    const button =
      document.querySelector(
        '#matchPopup button'
      );


    // Prevent double clicking reserve
    if (button) {

      button.disabled = true;

      button.textContent =
        '⏳ Reserving...';

    }


    fetch(`/reserve/${chairId}`, {

      method: 'POST',

      headers: {
        'Content-Type': 'application/json'
      }

    })

      .then(response => {

        if (!response.ok) {
          throw new Error(
            'Reservation request failed'
          );
        }

        return response.json();

      })

      .then(data => {

        if (data.status === 'ok') {

          closeMatchPopup();


          showToast(
            '💺 Seat reserved successfully!',
            'var(--success)'
          );


          /*
           * Go to reservations page
           * after the success message.
           */
          setTimeout(() => {

            window.location.href =
              '/reservations';

          }, 800);

        }

        else {

          if (button) {

            button.disabled = false;

            button.textContent =
              '💺 Reserve This Seat';

          }


          alert(
            data.msg ||
            'Unable to reserve this seat.'
          );

        }

      })

      .catch(error => {

        console.error(
          'Reservation error:',
          error
        );


        if (button) {

          button.disabled = false;

          button.textContent =
            '💺 Reserve This Seat';

        }


        alert(
          'Something went wrong while reserving the seat.'
        );

      });

  };



  /*
   * CLOSE MATCH POPUP
   */
  window.closeMatchPopup = function() {

    const popup =
      document.getElementById(
        'matchPopup'
      );

    if (popup) {
      popup.remove();
    }

  };



  // Drag to swipe
  card.addEventListener('mousedown', e => {

    if (
      e.target.tagName === 'BUTTON' ||
      e.target.tagName === 'A'
    ) {
      return;
    }

    isDragging = true;

    card.classList.add('swiping');

    startX = e.clientX;
    startY = e.clientY;

  });


  document.addEventListener('mousemove', e => {

    if (!isDragging) {
      return;
    }

    const dx =
      e.clientX - startX;

    const dy =
      e.clientY - startY;


    card.style.transform =
      `translateX(${dx}px) translateY(${dy}px) rotate(${dx * 0.07}deg)`;


    card.style.opacity =
      String(1 - Math.abs(dx) / 400);

  });


  document.addEventListener('mouseup', e => {

    if (!isDragging) {
      return;
    }

    isDragging = false;

    card.classList.remove('swiping');


    const dx =
      e.clientX - startX;


    if (dx > 80) {

      doSwipe('like');

    }

    else if (dx < -80) {

      doSwipe('dislike');

    }

    else {

      card.style.transform = '';
      card.style.opacity = '';

    }

  });



  // Touch swipe
  card.addEventListener('touchstart', e => {

    if (
      e.target.tagName === 'BUTTON' ||
      e.target.tagName === 'A'
    ) {
      return;
    }

    isDragging = true;

    card.classList.add('swiping');

    startX =
      e.touches[0].clientX;

    startY =
      e.touches[0].clientY;

  }, { passive: true });



  document.addEventListener('touchmove', e => {

    if (!isDragging) {
      return;
    }

    const dx =
      e.touches[0].clientX - startX;

    const dy =
      e.touches[0].clientY - startY;


    card.style.transform =
      `translateX(${dx}px) translateY(${dy}px) rotate(${dx * 0.07}deg)`;


    card.style.opacity =
      String(1 - Math.abs(dx) / 400);

  }, { passive: true });



  document.addEventListener('touchend', e => {

    if (!isDragging) {
      return;
    }

    isDragging = false;

    card.classList.remove('swiping');


    const dx =
      e.changedTouches[0].clientX - startX;


    if (dx > 80) {

      doSwipe('like');

    }

    else if (dx < -80) {

      doSwipe('dislike');

    }

    else {

      card.style.transform = '';
      card.style.opacity = '';

    }

  });

}