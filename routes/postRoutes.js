const express = require('express');
const router = express.Router();
const multer = require('multer');
const path = require('path');
const { v4: uuidv4 } = require('uuid');
const db = require('../db');
const { authenticateToken } = require('../auth');

const storage = multer.diskStorage({
  destination: (req, file, cb) => cb(null, 'uploads/'),
  filename: (req, file, cb) => {
    const ext = path.extname(file.originalname);
    cb(null, `${uuidv4()}${ext}`);
  }
});
const upload = multer({
  storage,
  limits: { fileSize: 100 * 1024 * 1024 },
  fileFilter: (req, file, cb) => {
    const allowed = /jpeg|jpg|png|gif|mp4|mov|avi|mkv/;
    const ext = allowed.test(path.extname(file.originalname).toLowerCase());
    const mime = allowed.test(file.mimetype);
    if (ext && mime) return cb(null, true);
    cb(new Error('Only images and videos'));
  }
});

// Create post
router.post('/', authenticateToken, upload.array('media', 10), (req, res) => {
  const { text, location, feeling, poll_options, visibility, content_type, shared_post_id, target_page_id } = req.body;
  let mediaFiles = [];
  if (req.files && req.files.length > 0) {
    mediaFiles = req.files.map(f => `/uploads/${f.filename}`);
  }
  const id = uuidv4();
  let type = content_type || 'text';
  if (mediaFiles.length > 0) {
    const first = mediaFiles[0].toLowerCase();
    if (first.match(/\.(mp4|mov|avi|mkv)$/)) type = 'video';
    else type = 'photo';
  }
  if (shared_post_id) type = 'shared';
  if (poll_options) type = 'poll';

  const pollOpts = poll_options ? JSON.stringify(typeof poll_options === 'string' ? JSON.parse(poll_options) : poll_options) : null;
  const pollVotes = JSON.stringify({});

  db.prepare(`
    INSERT INTO posts (id, author_id, content_type, text, media, location, feeling, poll_options, poll_votes, shared_post_id, visibility, is_sponsored, target_page_id)
    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
  `).run(id, req.user.id, type, text || '', JSON.stringify(mediaFiles), location || '', feeling || '', pollOpts, pollVotes, shared_post_id || null, visibility || 'public', 0, target_page_id || null);

  const post = db.prepare('SELECT * FROM posts WHERE id = ?').get(id);
  res.status(201).json(post);
});

// Get single post
router.get('/:id', authenticateToken, (req, res) => {
  const post = db.prepare('SELECT * FROM posts WHERE id = ?').get(req.params.id);
  if (!post) return res.status(404).json({ error: 'Not found' });
  res.json(post);
});

// Delete post
router.delete('/:id', authenticateToken, (req, res) => {
  const post = db.prepare('SELECT * FROM posts WHERE id = ?').get(req.params.id);
  if (!post || post.author_id !== req.user.id) return res.status(403).json({ error: 'Forbidden' });
  db.prepare('DELETE FROM posts WHERE id = ?').run(req.params.id);
  res.json({ message: 'Deleted' });
});

// Insights
router.get('/:id/insights', authenticateToken, (req, res) => {
  const post = db.prepare('SELECT * FROM posts WHERE id = ?').get(req.params.id);
  if (!post || post.author_id !== req.user.id) return res.status(403).json({ error: 'Not yours' });
  const likes = db.prepare('SELECT COUNT(*) as cnt FROM likes WHERE post_id = ?').get(post.id).cnt;
  const comments = db.prepare('SELECT COUNT(*) as cnt FROM comments WHERE post_id = ?').get(post.id).cnt;
  const shares = db.prepare('SELECT COUNT(*) as cnt FROM shares WHERE post_id = ?').get(post.id).cnt;
  const saves = db.prepare('SELECT COUNT(*) as cnt FROM saves WHERE post_id = ?').get(post.id).cnt;
  res.json({ likes, comments, shares, saves, total_reach: likes + comments*2 + shares*3 });
});

module.exports = router;