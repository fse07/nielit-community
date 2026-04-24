const db = require('./db');

// Features vector for a post given a user context
function getFeatureVector(userId, post) {
  const now = new Date();
  const createdAt = new Date(post.created_at);
  const hoursSince = (now - createdAt) / (1000 * 60 * 60);
  const recency = 1 / (1 + hoursSince);  // decay

  // creator affinity
  const affRow = db.prepare(
    'SELECT score FROM user_affinity WHERE user_id = ? AND target_user_id = ?'
  ).get(userId, post.author_id);
  const affinity = affRow ? affRow.score : 0;

  // content type one-hot
  const isText = post.content_type === 'text' ? 1 : 0;
  const isPhoto = post.content_type === 'photo' ? 1 : 0;
  const isVideo = post.content_type === 'video' ? 1 : 0;
  const isLink = post.content_type === 'link' ? 1 : 0;

  // engagement (likes + comments*2 + shares*3)
  const likes = db.prepare('SELECT COUNT(*) as cnt FROM likes WHERE post_id = ?').get(post.id).cnt;
  const comments = db.prepare('SELECT COUNT(*) as cnt FROM comments WHERE post_id = ?').get(post.id).cnt;
  const shares = db.prepare('SELECT COUNT(*) as cnt FROM shares WHERE post_id = ?').get(post.id).cnt;
  const engagement = Math.log(1 + likes + comments * 2 + shares * 3);

  const isSponsored = post.is_sponsored ? 1 : 0;

  // feature vector: [recency, affinity, isText, isPhoto, isVideo, isLink, engagement, isSponsored]
  return [recency, affinity, isText, isPhoto, isVideo, isLink, engagement, isSponsored];
}

// Get user’s current weights
function getUserWeights(userId) {
  let w = db.prepare('SELECT * FROM user_ranking_weights WHERE user_id = ?').get(userId);
  if (!w) {
    // insert defaults
    db.prepare(`INSERT INTO user_ranking_weights (user_id) VALUES (?)`).run(userId);
    w = db.prepare('SELECT * FROM user_ranking_weights WHERE user_id = ?').get(userId);
  }
  // order must match feature vector: recency, affinity, text, photo, video, link, engagement, sponsored
  return [
    w.w_recency,
    w.w_affinity,
    w.w_text,
    w.w_photo,
    w.w_video,
    w.w_link,
    w.w_engagement,
    w.w_sponsored
  ];
}

// Update weights using online logistic regression (positive feedback only)
function updateWeights(userId, features, label = 1, learningRate = 0.01) {
  const weights = getUserWeights(userId);
  // prediction = sigmoid(dot)
  const dot = weights.reduce((sum, w, i) => sum + w * features[i], 0);
  const sigmoid = 1 / (1 + Math.exp(-dot));
  const error = label - sigmoid;

  // new weights = old + lr * error * features
  const newWeights = weights.map((w, i) => w + learningRate * error * features[i]);

  db.prepare(`
    UPDATE user_ranking_weights SET
      w_recency = ?, w_affinity = ?, w_text = ?, w_photo = ?,
      w_video = ?, w_link = ?, w_engagement = ?, w_sponsored = ?,
      updated_at = CURRENT_TIMESTAMP
    WHERE user_id = ?
  `).run(...newWeights, userId);
}

// Compute feed score for a post given a user
function scorePost(userId, post) {
  const features = getFeatureVector(userId, post);
  const weights = getUserWeights(userId);
  return features.reduce((sum, feat, i) => sum + feat * weights[i], 0);
}

// Generate personalized feed for a user (top 200)
function getFeed(userId, limit = 200) {
  // Collect all candidate posts based on privacy rules
  const user = db.prepare('SELECT * FROM users WHERE id = ?').get(userId);
  if (!user) return [];

  // Friends list (accepted both directions)
  const friends = db.prepare(`
    SELECT friend_id FROM friendships WHERE user_id = ? AND status = 'accepted'
    UNION
    SELECT user_id FROM friendships WHERE friend_id = ? AND status = 'accepted'
  `).all(userId, userId).map(r => r.friend_id);

  // Friends of friends for visibility 'friends_of_friends'
  const fof = [];
  if (friends.length > 0) {
    const placeholders = friends.map(() => '?').join(',');
    const fofRows = db.prepare(`
      SELECT DISTINCT friend_id FROM friendships WHERE user_id IN (${placeholders}) AND status = 'accepted'
      AND friend_id != ?
      UNION
      SELECT DISTINCT user_id FROM friendships WHERE friend_id IN (${placeholders}) AND status = 'accepted'
      AND user_id != ?
    `).all(...friends, userId, ...friends, userId);
    fofRows.forEach(r => fof.push(r.friend_id));
  }

  // pages followed by the user
  const pagesFollowed = db.prepare('SELECT page_id FROM page_follows WHERE user_id = ?').all(userId).map(r => r.page_id);

  // All posts that are NOT only_me (except the user's own)
  const allPosts = db.prepare(`
    SELECT * FROM posts
    WHERE visibility != 'only_me' OR author_id = ?
  `).all(userId);

  const eligiblePosts = allPosts.filter(post => {
    const authorId = post.author_id;
    if (post.visibility === 'public') return true;
    if (authorId === userId) return true;  // own posts always visible
    if (post.visibility === 'friends') {
      return friends.includes(authorId);
    }
    if (post.visibility === 'friends_of_friends') {
      return friends.includes(authorId) || fof.includes(authorId);
    }
    if (post.visibility === 'only_me') return authorId === userId;
    // page posts: should be visible if user follows that page (target_page_id)
    if (post.target_page_id && pagesFollowed.includes(post.target_page_id)) return true;
    return false;
  });

  // Score & sort
  const scored = eligiblePosts.map(post => ({
    post,
    score: scorePost(userId, post)
  }));
  scored.sort((a, b) => b.score - a.score);
  const topPosts = scored.slice(0, limit).map(s => s.post);

  // Record impressions
  const insertImpr = db.prepare('INSERT INTO feed_impressions (user_id, post_id) VALUES (?, ?)');
  const insertMany = db.transaction((posts) => {
    for (const p of posts) {
      insertImpr.run(userId, p.id);
    }
  });
  insertMany(topPosts);

  return topPosts;
}

// Update affinities and weights after an interaction
function onInteraction(userId, post, interactionType) {
  // Update affinity to author
  const affScore = interactionType === 'like' ? 0.02 :
                    interactionType === 'comment' ? 0.03 :
                    interactionType === 'share' ? 0.04 :
                    interactionType === 'save' ? 0.025 : 0.01;
  const existing = db.prepare('SELECT * FROM user_affinity WHERE user_id = ? AND target_user_id = ?').get(userId, post.author_id);
  if (existing) {
    db.prepare('UPDATE user_affinity SET score = score + ?, updated_at = CURRENT_TIMESTAMP WHERE user_id = ? AND target_user_id = ?')
      .run(affScore, userId, post.author_id);
  } else {
    db.prepare('INSERT INTO user_affinity (user_id, target_user_id, score) VALUES (?, ?, ?)').run(userId, post.author_id, affScore);
  }

  // Update ranking weights with positive feedback
  const features = getFeatureVector(userId, post);
  updateWeights(userId, features, 1);

  // Also update content type preference (simple incremental boost)
  // Not strictly needed because weights already capture it, but we keep affinity table for friends/creators.
}

module.exports = {
  getFeed,
  scorePost,
  onInteraction
};