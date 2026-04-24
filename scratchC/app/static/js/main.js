/* Nielit Community - Frontend JS */
(function () {
  'use strict';

  // Get CSRF token
  function getCSRFToken() {
    const meta = document.querySelector('meta[name="csrf-token"]');
    return meta ? meta.getAttribute('content') : '';
  }

  // Generic fetch wrapper
  async function apiPost(url, data) {
    const body = new FormData();
    for (const k in data) body.append(k, data[k]);
    body.append('csrf_token', getCSRFToken());
    const resp = await fetch(url, {
      method: 'POST',
      body,
      credentials: 'same-origin',
      headers: { 'X-CSRFToken': getCSRFToken() },
    });
    return resp.json();
  }

  // Reactions
  document.addEventListener('click', async (e) => {
    const react = e.target.closest('.react-btn');
    if (react) {
      e.preventDefault();
      const postId = react.dataset.postId;
      const rtype = react.dataset.reaction || 'like';
      try {
        const r = await apiPost('/api/react', { post_id: postId, type: rtype });
        if (r.ok) {
          updateReactionUI(postId, r);
        }
      } catch (err) { console.error(err); }
    }

    // Hover reaction bar open on mobile tap
    const mainLike = e.target.closest('.post-action-like');
    if (mainLike) {
      const bar = mainLike.querySelector('.reaction-bar');
      if (bar && e.target.closest('.post-action-like-main')) {
        e.preventDefault();
        const postId = mainLike.dataset.postId;
        try {
          const r = await apiPost('/api/react', { post_id: postId, type: 'like' });
          if (r.ok) updateReactionUI(postId, r);
        } catch (err) { console.error(err); }
      }
    }

    // Save toggle
    const saveBtn = e.target.closest('.save-btn');
    if (saveBtn) {
      e.preventDefault();
      const postId = saveBtn.dataset.postId;
      try {
        const r = await apiPost('/api/save', { post_id: postId });
        if (r.ok) {
          saveBtn.classList.toggle('active', r.saved);
          const lbl = saveBtn.querySelector('.lbl');
          if (lbl) lbl.textContent = r.saved ? 'Saved' : 'Save';
        }
      } catch (err) { console.error(err); }
    }

    // Comment toggle
    const cmtBtn = e.target.closest('.comment-toggle');
    if (cmtBtn) {
      e.preventDefault();
      const section = document.getElementById('comments-' + cmtBtn.dataset.postId);
      if (section) {
        section.classList.toggle('open');
        if (section.classList.contains('open')) {
          const input = section.querySelector('input[name="content"]');
          if (input) setTimeout(() => input.focus(), 10);
        }
      }
    }

    // Menu toggle
    const menuBtn = e.target.closest('.post-menu-btn');
    if (menuBtn) {
      e.preventDefault();
      e.stopPropagation();
      document.querySelectorAll('.post-menu-dropdown.open').forEach(m => {
        if (m.previousElementSibling !== menuBtn) m.classList.remove('open');
      });
      const dd = menuBtn.nextElementSibling;
      if (dd) dd.classList.toggle('open');
    } else if (!e.target.closest('.post-menu-dropdown')) {
      document.querySelectorAll('.post-menu-dropdown.open').forEach(m => m.classList.remove('open'));
    }

    // Flash close
    const fc = e.target.closest('.flash-close');
    if (fc) fc.closest('.flash').remove();
  });

  function updateReactionUI(postId, r) {
    const btn = document.querySelector(`.post-action-like[data-post-id="${postId}"] .main-btn`);
    const countEl = document.querySelector(`.reaction-count-${postId}`);
    if (countEl) countEl.textContent = r.reaction_count + (r.reaction_count === 1 ? ' reaction' : ' reactions');
    if (btn) {
      btn.classList.remove('active', 'active-love', 'active-haha', 'active-wow');
      const label = btn.querySelector('.lbl');
      const ico = btn.querySelector('.ico');
      if (r.removed) {
        if (label) label.textContent = 'Like';
        if (ico) ico.textContent = '👍';
      } else {
        const map = {
          like: { t: 'Liked', e: '👍', cls: 'active' },
          love: { t: 'Love', e: '❤️', cls: 'active-love' },
          haha: { t: 'Haha', e: '😂', cls: 'active-haha' },
          wow:  { t: 'Wow', e: '😮', cls: 'active-wow' },
          sad:  { t: 'Sad', e: '😢', cls: 'active' },
          angry:{ t: 'Angry', e: '😡', cls: 'active' },
        };
        const cfg = map[r.reaction_type] || map.like;
        if (label) label.textContent = cfg.t;
        if (ico) ico.textContent = cfg.e;
        btn.classList.add(cfg.cls);
      }
    }
    // Close reaction bar
    const bar = document.querySelector(`.post-action-like[data-post-id="${postId}"] .reaction-bar`);
    if (bar) bar.classList.remove('open');
  }

  // Show reaction bar on hover for desktop, long-press for mobile
  document.querySelectorAll('.post-action-like').forEach(container => {
    const bar = container.querySelector('.reaction-bar');
    if (!bar) return;
    let timer;
    container.addEventListener('mouseenter', () => {
      timer = setTimeout(() => bar.classList.add('open'), 400);
    });
    container.addEventListener('mouseleave', () => {
      clearTimeout(timer);
      setTimeout(() => bar.classList.remove('open'), 300);
    });
  });

  // Comment submit
  document.addEventListener('submit', async (e) => {
    const form = e.target.closest('.comment-form');
    if (form) {
      e.preventDefault();
      const input = form.querySelector('input[name="content"]');
      const content = (input.value || '').trim();
      if (!content) return;
      const postId = form.dataset.postId;
      try {
        const r = await apiPost('/api/comment', { post_id: postId, content });
        if (r.ok) {
          input.value = '';
          const list = form.parentElement.querySelector('.comments-list');
          if (list) list.insertAdjacentHTML('beforeend', r.html);
          const cmtCount = document.querySelector(`.comment-count-${postId}`);
          if (cmtCount) cmtCount.textContent = r.comment_count;
        }
      } catch (err) { console.error(err); }
    }
  });

  // Track dwell time and video watch for ranking
  const observer = new IntersectionObserver((entries) => {
    entries.forEach(entry => {
      const post = entry.target;
      if (entry.isIntersecting) {
        post._dwellStart = performance.now();
        // Auto-play visible videos, pause invisible
        const video = post.querySelector('video');
        if (video && video.paused) {
          video.play().catch(() => {});
        }
      } else if (post._dwellStart) {
        const dwell = Math.floor(performance.now() - post._dwellStart);
        let watch = 0;
        const video = post.querySelector('video');
        if (video) {
          watch = Math.floor(video.currentTime);
          if (!video.paused) video.pause();
        }
        post._dwellStart = null;
        const postId = post.dataset.postId;
        if (postId && dwell > 500) {
          apiPost('/api/view-metrics', { post_id: postId, dwell_ms: dwell, watch_seconds: watch }).catch(() => {});
        }
      }
    });
  }, { threshold: 0.4 });

  document.querySelectorAll('.post[data-post-id]').forEach(p => observer.observe(p));

  // Infinite scroll
  const feedContainer = document.getElementById('feed-list');
  if (feedContainer && feedContainer.dataset.hasNext === '1') {
    let loading = false;
    let page = 1;
    window.addEventListener('scroll', async () => {
      if (loading) return;
      const bottom = document.documentElement.scrollHeight - window.innerHeight - window.scrollY;
      if (bottom < 600) {
        loading = true;
        page += 1;
        try {
          const resp = await fetch('/feed/more?page=' + page, { credentials: 'same-origin' });
          const html = await resp.text();
          if (html.trim()) {
            const wrap = document.createElement('div');
            wrap.innerHTML = html;
            wrap.querySelectorAll('.post[data-post-id]').forEach(p => {
              feedContainer.appendChild(p);
              observer.observe(p);
            });
            loading = false;
          }
        } catch (err) {
          console.error(err);
          loading = false;
        }
      }
    });
  }

  // Friend request buttons
  document.addEventListener('click', async (e) => {
    const btn = e.target.closest('[data-friend-action]');
    if (!btn) return;
    e.preventDefault();
    const action = btn.dataset.friendAction;
    const userId = btn.dataset.userId;
    const endpoints = {
      'request': '/u/friend-request',
      'accept': '/u/friend-accept',
      'reject': '/u/friend-reject',
    };
    const url = endpoints[action];
    if (!url) return;
    try {
      const r = await apiPost(url, { user_id: userId });
      if (r.ok) {
        const label = {
          'pending_out': '✓ Request sent',
          'accepted': '✓ Friends',
          'none': 'Add friend',
        }[r.status] || 'Updated';
        btn.textContent = label;
        btn.disabled = true;
      }
    } catch (err) { console.error(err); }
  });

  // Auto-close flash messages after 5 seconds
  document.querySelectorAll('.flash').forEach(f => {
    setTimeout(() => {
      f.style.transition = 'opacity .3s';
      f.style.opacity = '0';
      setTimeout(() => f.remove(), 300);
    }, 5000);
  });

  // Poll votes - immediate submit
  document.querySelectorAll('.poll-form').forEach(form => {
    form.addEventListener('click', (e) => {
      if (e.target.closest('.poll-option')) {
        setTimeout(() => form.submit(), 50);
      }
    });
  });

})();
