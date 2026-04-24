const express = require('express');
const router = express.Router();
const { v4: uuidv4 } = require('uuid');
const db = require('../db');
const { authenticateToken } = require('../auth');
const { onInteraction } = require('../ranking');

// Like / unlike
router.post('/posts/:id/like', authenticateToken, (req, res) => {
  const post = db.prepare('SELECT * FROM posts WHERE id = ?').get(req.params.id);
  if (!post) return res.status(404).json({ error: 'Post not found' });
  const exists = db.prepare('SELECT * FROM likes WHERE user_id = ? AND post_id = ?').get(req.user.id, post.id);
  if (exists) {
    db.prepare('DELETE FROM likes WHERE user_id = ? AND post_id = ?').run(req.user.id, post.id);
    res.json({ liked: false });
  } else {
    db.prepare('INSERT INTO likes (user_id, post_id) VALUES (?,?)').run(req.user.id, post.id);
    onInteraction(req.user.id, post, 'like');
    res.json({ liked: true });
  }
});

// Comment
router.post('/posts/:id/comment', authenticateToken, (req, res) => {
  const post = db.prepare('SELECT * FROM posts WHERE id = ?').get(req.params.id);
  if (!post) return res.status(404).json({ error: 'Post not found' });
  const { text } = req.body;
  if (!text) return res.status(400).json({ error: 'Comment text required' });
  const commentId = uuidv4();
  db.prepare('INSERT INTO comments (id, user_id, post_id, text) VALUES (?,?,?,?)').run(commentId, req.user.id, post.id, text);
  onInteraction(req.user.id, post, 'comment');
  res.status(201).json({ id: commentId, text, created_at: new Date().toISOString() });
});

// Get comments
router.get('/posts/:id/comments', authenticateToken, (req, res) => {
  const comments = db.prepare(`
    SELECT c.id, c.text, c.created_at, u.username, u.full_name, u.profile_pic
    FROM comments c JOIN users u ON c.user_id = u.id
    WHERE c.post_id = ? ORDER BY c.created_at DESC
  `).all(req.params.id);
  res.json(comments);
});

// Share
router.post('/posts/:id/share', authenticateToken, (req, res) => {
  const post = db.prepare('SELECT * FROM posts WHERE id = ?').get(req.params.id);
  if (!post) return res.status(404).json({ error: 'Post not found' });
  const shareId = uuidv4();
  db.prepare('INSERT INTO shares (id, user_id, post_id) VALUES (?,?,?)').run(shareId, req.user.id, post.id);
  onInteraction(req.user.id, post, 'share');
  res.json({ shared: true });
});

// Save
router.post('/posts/:id/save', authenticateToken, (req, res) => {
  const post = db.prepare('SELECT * FROM posts WHERE id = ?').get(req.params.id);
  if (!post) return res.status(404).json({ error: 'Not found' });
  const existing = db.prepare('SELECT * FROM saves WHERE user_id = ? AND post_id = ?').get(req.user.id, post.id);
  if (existing) {
    db.prepare('DELETE FROM saves WHERE user_id = ? AND post_id = ?').run(req.user.id, post.id);
    res.json({ saved: false });
  } else {
    db.prepare('INSERT INTO saves (user_id, post_id) VALUES (?,?)').run(req.user.id, post.id);
    onInteraction(req.user.id, post, 'save');
    res.json({ saved: true });
  }
});

// Video watch
router.post('/video/watch', authenticateToken, (req, res) => {
  const { post_id, watch_seconds } = req.body;
  if (!post_id) return res.status(400).json({ error: 'post_id required' });
  const post = db.prepare('SELECT * FROM posts WHERE id = ?').get(post_id);
  if (post && post.content_type === 'video') {
    db.prepare('INSERT INTO video_watches (user_id, post_id, watch_seconds) VALUES (?,?,?)').run(req.user.id, post_id, watch_seconds || 0);
    if (watch_seconds > 3) onInteraction(req.user.id, post, 'watch');
  }
  res.json({ ok: true });
});

module.exports = router;