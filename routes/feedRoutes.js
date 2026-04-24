const express = require('express');
const router = express.Router();
const db = require('../db');
const { authenticateToken } = require('../auth');
const { getFeed } = require('../ranking');

// GET /api/feed
router.get('/', authenticateToken, (req, res) => {
  const page = parseInt(req.query.page) || 1;
  const limit = parseInt(req.query.limit) || 20;
  const rankedPosts = getFeed(req.user.id, 200);
  const start = (page - 1) * limit;
  const paginated = rankedPosts.slice(start, start + limit);

  const enriched = paginated.map(post => {
    const author = db.prepare('SELECT id, username, full_name, profile_pic FROM users WHERE id = ?').get(post.author_id);
    const liked = db.prepare('SELECT 1 FROM likes WHERE user_id = ? AND post_id = ?').get(req.user.id, post.id) ? true : false;
    const saved = db.prepare('SELECT 1 FROM saves WHERE user_id = ? AND post_id = ?').get(req.user.id, post.id) ? true : false;
    const likesCount = db.prepare('SELECT COUNT(*) as cnt FROM likes WHERE post_id = ?').get(post.id).cnt;
    const commentsCount = db.prepare('SELECT COUNT(*) as cnt FROM comments WHERE post_id = ?').get(post.id).cnt;
    const sharesCount = db.prepare('SELECT COUNT(*) as cnt FROM shares WHERE post_id = ?').get(post.id).cnt;
    let media = [];
    try { media = JSON.parse(post.media); } catch(e){}
    return { ...post, author, liked, saved, likes_count: likesCount, comments_count: commentsCount, shares_count: sharesCount, media };
  });
  res.json({ posts: enriched, hasMore: start + limit < rankedPosts.length });
});

module.exports = router;