const express = require('express');
const router = express.Router();
const { v4: uuidv4 } = require('uuid');
const bcrypt = require('bcryptjs');
const db = require('../db');
const { generateToken } = require('../auth');

// POST /api/auth/signup
router.post('/signup', (req, res) => {
  const { username, email, password, full_name } = req.body;
  if (!username || !email || !password) return res.status(400).json({ error: 'Missing fields' });
  const existing = db.prepare('SELECT id FROM users WHERE username = ? OR email = ?').get(username, email);
  if (existing) return res.status(409).json({ error: 'Username or email already exists' });
  const hash = bcrypt.hashSync(password, 10);
  const id = uuidv4();
  db.prepare('INSERT INTO users (id, username, email, password_hash, full_name) VALUES (?,?,?,?,?)')
    .run(id, username, email, hash, full_name || username);
  // init ranking weights
  db.prepare('INSERT INTO user_ranking_weights (user_id) VALUES (?)').run(id);
  const token = generateToken({ id, username });
  res.status(201).json({ token, user: { id, username, email, full_name } });
});

// POST /api/auth/login
router.post('/login', (req, res) => {
  const { username, password } = req.body;
  const user = db.prepare('SELECT * FROM users WHERE username = ?').get(username);
  if (!user) return res.status(401).json({ error: 'Invalid credentials' });
  if (!bcrypt.compareSync(password, user.password_hash)) return res.status(401).json({ error: 'Invalid credentials' });
  const token = generateToken({ id: user.id, username: user.username });
  res.json({ token, user: { id: user.id, username: user.username, email: user.email, full_name: user.full_name } });
});

module.exports = router;