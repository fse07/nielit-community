const API = '';
let token = localStorage.getItem('token');
let currentUser = null;

// Initial check
if (token) {
  fetchUserAndShowApp();
}

async function fetchUserAndShowApp() {
  try {
    const res = await fetch(`${API}/api/users/me`, { headers: { Authorization: `Bearer ${token}` } });
    if (res.ok) {
      currentUser = await res.json();
      showApp();
      loadFeed();
    } else {
      logout();
    }
  } catch { logout(); }
}

function showApp() {
  document.getElementById('auth-container').style.display = 'none';
  document.getElementById('main-app').style.display = 'block';
  document.getElementById('user-info').innerHTML = `<strong>${currentUser.full_name || currentUser.username}</strong>`;
}

function logout() {
  localStorage.removeItem('token');
  token = null;
  currentUser = null;
  document.getElementById('auth-container').style.display = 'flex';
  document.getElementById('main-app').style.display = 'none';
}

function showSignup() { document.getElementById('login-form').style.display='none'; document.getElementById('signup-form').style.display='block'; }
function showLogin() { document.getElementById('signup-form').style.display='none'; document.getElementById('login-form').style.display='block'; }

async function login() {
  const username = document.getElementById('login-username').value;
  const password = document.getElementById('login-password').value;
  const res = await fetch(`${API}/api/auth/login`, {
    method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify({username, password})
  });
  if (res.ok) {
    const data = await res.json();
    token = data.token;
    localStorage.setItem('token', token);
    fetchUserAndShowApp();
  } else alert('Login failed');
}

async function signup() {
  const username = document.getElementById('signup-username').value;
  const email = document.getElementById('signup-email').value;
  const password = document.getElementById('signup-password').value;
  const full_name = document.getElementById('signup-fullname').value;
  const res = await fetch(`${API}/api/auth/signup`, {
    method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify({username, email, password, full_name})
  });
  if (res.ok) {
    const data = await res.json();
    token = data.token;
    localStorage.setItem('token', token);
    fetchUserAndShowApp();
  } else alert('Signup failed');
}

document.getElementById('logout-btn').addEventListener('click', logout);

// Feed loading
async function loadFeed(page = 1, append = false) {
  const res = await fetch(`${API}/api/feed?page=${page}&limit=20`, { headers: { Authorization: `Bearer ${token}` } });
  if (!res.ok) return;
  const data = await res.json();
  const container = document.getElementById('feed-container');
  if (!append) container.innerHTML = '';
  data.posts.forEach(post => container.appendChild(createPostCard(post)));
  if (data.hasMore) {
    const loadMore = document.createElement('button');
    loadMore.textContent = 'Load More';
    loadMore.onclick = () => { loadMore.remove(); loadFeed(page+1, true); };
    container.appendChild(loadMore);
  }
}

function createPostCard(post) {
  const div = document.createElement('div');
  div.className = 'post-card';
  let mediaHTML = '';
  if (post.media && post.media.length) {
    mediaHTML = '<div class="post-media">';
    post.media.forEach(url => {
      if (url.match(/\.(mp4|mov|avi|mkv)$/i)) {
        mediaHTML += `<video controls onplay="reportWatch('${post.id}', this)"><source src="${url}" type="video/mp4"></video>`;
      } else {
        mediaHTML += `<img src="${url}" alt="media" />`;
      }
    });
    mediaHTML += '</div>';
  }
  const pollHTML = post.content_type === 'poll' ? `<div class="poll">${JSON.parse(post.poll_options).map((opt,i) => `<button>${opt}</button>`).join('')}</div>` : '';
  const locationHTML = post.location ? `<div class="post-location">📍 ${post.location}</div>` : '';
  const feelingHTML = post.feeling ? `<div class="post-feeling">😊 Feeling ${post.feeling}</div>` : '';
  div.innerHTML = `
    <div class="post-header">
      <div class="post-avatar"></div>
      <div><span class="post-username">${post.author.full_name || post.author.username}</span>
      <span class="post-time">${timeSince(post.created_at)}</span></div>
    </div>
    <div class="post-text">${post.text || ''}</div>
    ${mediaHTML}
    ${pollHTML}
    ${locationHTML}
    ${feelingHTML}
    <div class="post-actions">
      <button class="action-btn ${post.liked ? 'liked' : ''}" onclick="toggleLike('${post.id}', this)">👍 Like (${post.likes_count})</button>
      <button class="action-btn" onclick="toggleComment('${post.id}')">💬 Comment (${post.comments_count})</button>
      <button class="action-btn" onclick="sharePost('${post.id}')">↗️ Share (${post.shares_count})</button>
      <button class="action-btn ${post.saved ? 'saved' : ''}" onclick="toggleSave('${post.id}', this)">🔖 Save</button>
      ${post.author_id === currentUser.id ? `<button class="action-btn" onclick="viewInsights('${post.id}')">📊 Insights</button>` : ''}
    </div>
    <div class="comments-section" id="comments-${post.id}" style="display:none"></div>
  `;
  return div;
}

function timeSince(dateStr) {
  const now = new Date();
  const then = new Date(dateStr);
  const seconds = Math.floor((now - then) / 1000);
  if (seconds < 60) return 'just now';
  const mins = Math.floor(seconds / 60);
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.floor(hours / 24)}d ago`;
}

async function toggleLike(postId, btn) {
  const res = await fetch(`${API}/api/posts/${postId}/like`, { method: 'POST', headers: { Authorization: `Bearer ${token}` } });
  if (!res.ok) return;
  const data = await res.json();
  btn.classList.toggle('liked', data.liked);
  btn.textContent = `👍 Like (${data.liked ? '1' : '0'})`; // simplified, will refresh on next load
  loadFeed(1); // refresh to update counts
}

async function toggleComment(postId) {
  const section = document.getElementById(`comments-${postId}`);
  section.style.display = section.style.display === 'none' ? 'block' : 'none';
  if (section.style.display === 'block' && section.children.length === 0) {
    const res = await fetch(`${API}/api/posts/${postId}/comments`, { headers: { Authorization: `Bearer ${token}` } });
    const comments = await res.json();
    section.innerHTML = comments.map(c => `<p><strong>${c.full_name}</strong>: ${c.text}</p>`).join('') +
      `<input type="text" id="comment-input-${postId}" placeholder="Write a comment..." />
       <button onclick="submitComment('${postId}')">Post</button>`;
  }
}

async function submitComment(postId) {
  const input = document.getElementById(`comment-input-${postId}`);
  const text = input.value.trim();
  if (!text) return;
  await fetch(`${API}/api/posts/${postId}/comment`, {
    method: 'POST', headers: { 'Content-Type':'application/json', Authorization: `Bearer ${token}` },
    body: JSON.stringify({text})
  });
  input.value = '';
  toggleComment(postId); // refresh
}

async function sharePost(postId) {
  await fetch(`${API}/api/posts/${postId}/share`, { method: 'POST', headers: { Authorization: `Bearer ${token}` } });
  loadFeed(1);
}

async function toggleSave(postId, btn) {
  const res = await fetch(`${API}/api/posts/${postId}/save`, { method: 'POST', headers: { Authorization: `Bearer ${token}` } });
  const data = await res.json();
  btn.classList.toggle('saved', data.saved);
}

async function viewInsights(postId) {
  const res = await fetch(`${API}/api/posts/${postId}/insights`, { headers: { Authorization: `Bearer ${token}` } });
  const data = await res.json();
  alert(`Likes:${data.likes}, Comments:${data.comments}, Shares:${data.shares}, Saves:${data.saves}`);
}

function reportWatch(postId, videoEl) {
  videoEl.addEventListener('timeupdate', function() {
    if (videoEl.currentTime > 0) {
      fetch(`${API}/api/video/watch`, {
        method: 'POST', headers: { 'Content-Type':'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify({post_id: postId, watch_seconds: videoEl.currentTime})
      });
      videoEl.removeEventListener('timeupdate', arguments.callee);
    }
  });
}

// Post creation modal
function openCreatePost() { document.getElementById('post-modal').style.display = 'flex'; }
function closeCreatePost() { document.getElementById('post-modal').style.display = 'none'; }
function previewMedia() {
  const preview = document.getElementById('media-preview');
  preview.innerHTML = '';
  const files = document.getElementById('media-upload').files;
  for (let f of files) {
    const reader = new FileReader();
    reader.onload = (e) => {
      if (f.type.startsWith('video')) {
        preview.innerHTML += `<video src="${e.target.result}" controls width="100"></video>`;
      } else {
        preview.innerHTML += `<img src="${e.target.result}" width="100"/>`;
      }
    };
    reader.readAsDataURL(f);
  }
}
async function createPost() {
  const formData = new FormData();
  const text = document.getElementById('post-text').value;
  formData.append('text', text);
  const location = document.getElementById('post-location').value;
  if (location) formData.append('location', location);
  const feeling = document.getElementById('post-feeling').value;
  if (feeling) formData.append('feeling', feeling);
  formData.append('visibility', document.getElementById('post-visibility').value);
  const files = document.getElementById('media-upload').files;
  for (let f of files) formData.append('media', f);
  const poll1 = document.getElementById('poll-opt1').value;
  const poll2 = document.getElementById('poll-opt2').value;
  if (poll1 && poll2) formData.append('poll_options', JSON.stringify([poll1, poll2]));
  const res = await fetch(`${API}/api/posts`, { method: 'POST', headers: { Authorization: `Bearer ${token}` }, body: formData });
  if (res.ok) {
    closeCreatePost();
    loadFeed(1);
  } else alert('Error creating post');
}

// Navigation stubs
document.getElementById('nav-friends').addEventListener('click', () => alert('Friend management coming soon'));
document.getElementById('nav-pages').addEventListener('click', () => alert('Page features under construction'));