"""
Core feed ranking algorithm.

This module implements a personalized ranking system similar in shape to how
production feeds (Facebook, Instagram, Twitter) combine signals:

    score = w_aff  * affinity(user, author_or_source)
          + w_eng  * engagement_velocity(post)
          + w_rec  * recency_decay(post)
          + w_typ  * user_type_preference(post.type)
          + noise  * exploration_bonus()

Every user has their own weights row (UserFeedWeights), which is updated
after each interaction. Affinity scores (UserAffinity) capture how often
the user engages with specific authors/pages/groups.

This is not a neural net, but it's the real structure of many production
relevance systems: hand-crafted features, learned weights per user, linear
combination, plus randomization for discovery.
"""
import math
import random
from datetime import datetime, timedelta
from sqlalchemy import or_, and_, func
from flask import current_app

from ..extensions import db
from ..models import (
    User, Post, Friendship, PageFollow, GroupMember,
    UserAffinity, UserFeedWeights, Reaction, Comment, PostView,
)


# ------- WEIGHT HELPERS -------

def get_or_create_weights(user_id):
    w = db.session.query(UserFeedWeights).filter_by(user_id=user_id).first()
    if w is None:
        w = UserFeedWeights(user_id=user_id)
        db.session.add(w)
        db.session.commit()
    return w


def bump_affinity(user_id, target_type, target_id, delta):
    """Increase affinity score toward a target (user/page/group)."""
    if target_id is None:
        return
    row = db.session.query(UserAffinity).filter_by(
        user_id=user_id, target_type=target_type, target_id=target_id
    ).first()
    if row is None:
        row = UserAffinity(user_id=user_id, target_type=target_type, target_id=target_id, score=0.0)
        db.session.add(row)
    row.score = min(row.score + delta, 50.0)  # cap
    db.session.commit()


def bump_type_preference(user_id, post_type, delta=0.05):
    """Nudge the per-user type weight based on what they engaged with."""
    w = get_or_create_weights(user_id)
    attr = {
        "text": "w_type_text",
        "photo": "w_type_photo",
        "album": "w_type_photo",
        "video": "w_type_video",
        "short_video": "w_type_video",
        "link": "w_type_link",
        "poll": "w_type_poll",
    }.get(post_type)
    if not attr:
        return
    cur = getattr(w, attr)
    new = max(0.3, min(2.0, cur + delta))
    setattr(w, attr, new)
    db.session.commit()


def record_interaction(user_id, post, interaction_type):
    """
    Called by routes when user reacts/comments/shares/saves/views.
    Strengthens affinity toward the author/page/group and adjusts type weights.
    """
    deltas = {
        "reaction": 1.0,
        "comment": 2.0,
        "share": 3.0,
        "save": 1.5,
        "view": 0.1,
        "watch_long": 0.4,   # watched > 15s of a video
        "dwell_long": 0.2,   # dwelled > 3s on post
    }
    delta = deltas.get(interaction_type, 0.3)

    # Affinity on author
    bump_affinity(user_id, "user", post.author_id, delta)

    # Affinity on page/group if posted via one
    if post.page_id:
        bump_affinity(user_id, "page", post.page_id, delta)
    if post.group_id:
        bump_affinity(user_id, "group", post.group_id, delta)

    # Type preference
    if interaction_type in ("reaction", "comment", "share", "save", "watch_long", "dwell_long"):
        bump_type_preference(user_id, post.post_type, delta * 0.03)


# ------- CANDIDATE RETRIEVAL -------

def _visibility_filter(user, candidate_authors_friends):
    """
    Build a SQLAlchemy filter that enforces post visibility rules.
    A user can see a post if:
      - visibility='public'                         (always)
      - visibility='friends' AND author is friend   (or author is self)
      - visibility='friends_of_friends' AND author is friend OR friend-of-friend
      - visibility='only_me' AND author is self
    """
    from ..models import Post
    user_id = user.id
    friend_ids = set(candidate_authors_friends)

    return or_(
        Post.visibility == "public",
        Post.author_id == user_id,
        and_(Post.visibility == "friends", Post.author_id.in_(friend_ids)),
        and_(Post.visibility == "friends_of_friends", Post.author_id.in_(friend_ids)),
    )


def _friends_of_friends(user_id, direct_friends):
    """Approximate friends-of-friends set."""
    if not direct_friends:
        return set()
    rows = db.session.query(Friendship).filter(
        Friendship.status == "accepted",
        or_(
            Friendship.user_id.in_(direct_friends),
            Friendship.friend_id.in_(direct_friends),
        ),
    ).all()
    fof = set()
    for r in rows:
        fof.add(r.user_id)
        fof.add(r.friend_id)
    fof.discard(user_id)
    return fof


def fetch_candidate_posts(user, limit=None):
    """
    Gather a candidate pool of posts from user's graph:
      - Friends' posts (Public/Friends/FoF)
      - Public pages they follow
      - Groups they're members of
      - Public posts by non-friends (for "recommended" discovery)
      - Sponsored posts (always candidates)
      - Their own posts
    Returns a list of Post objects (not yet scored).
    """
    if limit is None:
        limit = current_app.config["FEED_CANDIDATE_POOL_SIZE"]

    friend_ids = set(user.friends_ids())
    fof_ids = _friends_of_friends(user.id, friend_ids)
    visible_authors = friend_ids | fof_ids

    followed_pages = [f.page_id for f in db.session.query(PageFollow).filter_by(user_id=user.id).all()]
    member_groups = [m.group_id for m in db.session.query(GroupMember).filter_by(user_id=user.id).all()]

    # Only candidates from the last 10 days, to keep the pool sharp
    cutoff = datetime.utcnow() - timedelta(days=10)

    q = db.session.query(Post).filter(
        Post.is_deleted.is_(False),
        Post.created_at >= cutoff,
    )

    # Visibility rules
    q = q.filter(
        or_(
            # Sponsored always visible
            Post.is_sponsored.is_(True),
            # Own posts
            Post.author_id == user.id,
            # Public posts
            Post.visibility == "public",
            # Friends visibility + author is friend
            and_(Post.visibility == "friends", Post.author_id.in_(friend_ids)),
            # FoF visibility + author in friends or FoF
            and_(Post.visibility == "friends_of_friends", Post.author_id.in_(visible_authors)),
            # Posts in groups user is member of (group posts ignore friends visibility)
            and_(Post.group_id.isnot(None), Post.group_id.in_(member_groups)),
            # Posts by pages user follows (pages post publicly)
            and_(Post.page_id.isnot(None), Post.page_id.in_(followed_pages)),
        )
    )

    q = q.order_by(Post.created_at.desc()).limit(limit)
    return q.all()


# ------- SCORING -------

def affinity_score(user_id, post, cache):
    """Lookup pre-fetched affinity scores with cache dict."""
    score = 0.0
    key = ("user", post.author_id)
    score += cache.get(key, 0.0)
    if post.page_id:
        score += cache.get(("page", post.page_id), 0.0) * 0.8
    if post.group_id:
        score += cache.get(("group", post.group_id), 0.0) * 0.8
    return score


def engagement_velocity(post):
    """Engagement-per-hour since creation, log-scaled."""
    age_hours = max(0.5, (datetime.utcnow() - post.created_at).total_seconds() / 3600.0)
    raw = post.engagement_score()
    return math.log1p(raw / age_hours)


def recency_decay(post, half_life_hours=18.0):
    """exp decay with configurable half-life."""
    age_hours = max(0.0, (datetime.utcnow() - post.created_at).total_seconds() / 3600.0)
    return math.pow(0.5, age_hours / half_life_hours)


def type_preference(post_type, weights):
    return {
        "text": weights.w_type_text,
        "photo": weights.w_type_photo,
        "album": weights.w_type_photo,
        "video": weights.w_type_video,
        "short_video": weights.w_type_video * 1.1,
        "link": weights.w_type_link,
        "poll": weights.w_type_poll,
        "shared": weights.w_type_text * 0.95,
        "event": weights.w_type_text * 1.1,
        "birthday": weights.w_type_text * 1.2,
        "sponsored": 1.0,
    }.get(post_type, 1.0)


def already_seen_penalty(user_id, post_id, seen_set):
    """Apply a penalty if user has already seen this post. Strong if interacted."""
    if post_id in seen_set:
        return -0.8
    return 0.0


def score_post(user, post, weights, affinity_cache, seen_set, rng):
    """Compute a single post's rank score."""
    aff = affinity_score(user.id, post, affinity_cache)
    eng = engagement_velocity(post)
    rec = recency_decay(post)
    typ = type_preference(post.post_type, weights)

    score = (
        weights.w_affinity * aff
        + weights.w_engagement * eng
        + weights.w_recency * rec * 3.0
        + 0.4 * typ
    )

    # Boost friends' content slightly
    if post.author_id in user._cached_friend_ids:
        score += 0.6

    # Own posts go lower (you don't need to see yourself much)
    if post.author_id == user.id:
        score -= 0.4

    # Sponsored: inject a moderate boost so it appears, not dominates
    if post.is_sponsored:
        score += 1.0

    # Diversity penalty for posts already seen
    score += already_seen_penalty(user.id, post.id, seen_set)

    # Exploration noise (different every refresh -> different order)
    score += weights.w_exploration * rng.random()

    return score


# ------- MAIN ENTRY -------

def build_feed_for_user(user, page=1, page_size=None):
    """
    Return a list of (post, score) tuples for the user's ranked feed.
    Paginated.
    """
    if page_size is None:
        page_size = current_app.config["FEED_PAGE_SIZE"]

    weights = get_or_create_weights(user.id)

    # Cache friend ids on user (used during scoring)
    user._cached_friend_ids = set(user.friends_ids())

    candidates = fetch_candidate_posts(user)
    if not candidates:
        return []

    # Pre-fetch affinity rows in one query
    aff_rows = db.session.query(UserAffinity).filter_by(user_id=user.id).all()
    affinity_cache = {(r.target_type, r.target_id): r.score for r in aff_rows}

    # Pre-fetch seen set (posts viewed in last 24h)
    seen_cutoff = datetime.utcnow() - timedelta(hours=24)
    seen_rows = db.session.query(PostView.post_id).filter(
        PostView.user_id == user.id,
        PostView.created_at >= seen_cutoff,
    ).all()
    seen_set = {r[0] for r in seen_rows}

    # Deterministic-per-user seed but varies per page & hour so refresh gives new order
    rng = random.Random(f"{user.id}:{page}:{datetime.utcnow().hour}")

    scored = [(p, score_post(user, p, weights, affinity_cache, seen_set, rng)) for p in candidates]
    scored.sort(key=lambda x: x[1], reverse=True)

    # Diversity: ensure we don't show 5 posts from same author back-to-back
    diversified = _diversify(scored, max_consecutive_same_author=1)

    # Pagination
    start = (page - 1) * page_size
    end = start + page_size
    return diversified[start:end]


def _diversify(scored_posts, max_consecutive_same_author=1):
    """Reorder so no author appears more than N times in a row."""
    result = []
    remaining = list(scored_posts)
    last_author = None
    consecutive = 0
    while remaining:
        picked = None
        for i, (p, s) in enumerate(remaining):
            if p.author_id != last_author or consecutive < max_consecutive_same_author:
                picked = (i, p, s)
                break
        if picked is None:
            picked = (0, remaining[0][0], remaining[0][1])
        idx, p, s = picked
        result.append((p, s))
        if p.author_id == last_author:
            consecutive += 1
        else:
            consecutive = 1
            last_author = p.author_id
        remaining.pop(idx)
    return result
