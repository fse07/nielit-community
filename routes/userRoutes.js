const express = require('express');
const router = express.Router();
const db = require('../db');
const { authenticateToken } = require('../auth');

// GET /api/users/me
router.get('/me', authenticateToken, (req, res) => {
  const user = db.prepare('SELECT id, username, email, full_name, profile_pic, created_at FROM users WHERE id = ?').get(req.user.id);
  res.json(user);
});

// POST /api/friends/request
router.post('/friends/request', authenticateToken, (req, res) => {
  const { friendUsername } = req.body;
  const friend = db.prepare('SELECT id FROM users WHERE username = ?').get(friendUsername);
  if (!friend) return res.status(404).json({ error: 'User not found' });
  if (friend.id === req.user.id) return res.status(400).json({ error: 'Cannot friend yourself' });
  const existing = db.prepare('SELECT * FROM friendships WHERE (user_id = ? AND friend_id = ?) OR (user_id = ? AND friend_id = ?)')
    .get(req.user.id, friend.id, friend.id, req.user.id);
  if (existing) {
    if (existing.status === 'accepted') return res.status(400).json({ error: 'Already friends' });
    if (existing.status === 'pending') return res.status(400).json({ error: 'Request already sent' });
  }
  db.prepare('INSERT INTO friendships (user_id, friend_id, status) VALUES (?, ?, ?)').run(req.user.id, friend.id, 'pending');
  res.status(201).json({ message: 'Friend request sent' });
});

// GET /api/friends/pending
router.get('/friends/pending', authenticateToken, (req, res) => {
  const incoming = db.prepare('SELECT u.id, u.username, u.full_name FROM friendships f JOIN users u ON f.user_id = u.id WHERE f.friend_id = ? AND f.status = ?').all(req.user.id, 'pending');
  res.json(incoming);
});

// POST /api/friends/accept
router.post('/friends/accept', authenticateToken, (req, res) => {
  const { requesterId } = req.body;
  const updated = db.prepare('UPDATE friendships SET status = ? WHERE user_id = ? AND friend_id = ? AND status = ?').run('accepted', requesterId, req.user.id, 'pending');
  if (updated.changes === 0) return res.status(400).json({ error: 'No pending request' });
  res.json({ message: 'Friend request accepted' });
});

// GET /api/friends
router.get('/friends', authenticateToken, (req, res) => {
  const friends = db.prepare(`
    SELECT u.id, u.username, u.full_name, u.profile_pic FROM friendships f
    JOIN users u ON (f.friend_id = u.id OR f.user_id = u.id)
    WHERE (f.user_id = ? OR f.friend_id = ?) AND f.status = 'accepted' AND u.id != ?
  `).all(req.user.id, req.user.id, req.user.id);
  res.json(friends);
});

// Pages
router.post('/pages', authenticateToken, (req, res) => {
  const { name } = req.body;
  const id = require('uuid').v4();
  db.prepare('INSERT INTO pages (id, name, owner_id) VALUES (?, ?, ?)').run(id, name, req.user.id);
  res.status(201).json({ id, name });
});

router.post('/pages/:pageId/follow', authenticateToken, (req, res) => {
  const { pageId } = req.params;
  const page = db.prepare('SELECT * FROM pages WHERE id = ?').get(pageId);
  if (!page) return res.status(404).json({ error: 'Page not found' });
  db.prepare('INSERT OR IGNORE INTO page_follows (user_id, page_id) VALUES (?, ?)').run(req.user.id, pageId);
  res.json({ message: 'Followed' });
});

router.post('/pages/:pageId/unfollow', authenticateToken, (req, res) => {
  const { pageId } = req.params;
  db.prepare('DELETE FROM page_follows WHERE user_id = ? AND page_id = ?').run(req.user.id, pageId);
  res.json({ message: 'Unfollowed' });
});

module.exports = router;