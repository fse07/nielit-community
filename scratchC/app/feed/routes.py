"""Feed routes."""
from datetime import datetime
from flask import Blueprint, render_template, request, jsonify
from flask_login import login_required, current_user
from sqlalchemy import or_, func

from ..extensions import db
from ..models import Post, User, Page, Group, PostView, Save, Notification, Friendship, PageFollow
from .ranking import build_feed_for_user, record_interaction

bp = Blueprint("feed", __name__)


@bp.route("/feed")
@login_required
def home():
    page = max(1, int(request.args.get("page", 1)))
    ranked = build_feed_for_user(current_user, page=page)
    posts = [r[0] for r in ranked]

    # Record that the user saw these posts
    if posts:
        for p in posts:
            db.session.add(PostView(post_id=p.id, user_id=current_user.id))
        # Increment view counts
        post_ids = [p.id for p in posts]
        db.session.query(Post).filter(Post.id.in_(post_ids)).update(
            {Post.view_count: Post.view_count + 1}, synchronize_session=False
        )
        db.session.commit()

    # Sidebar data
    unread_notif = db.session.query(func.count(Notification.id)).filter_by(
        user_id=current_user.id, is_read=False
    ).scalar()
    pending_requests = db.session.query(Friendship).filter_by(
        friend_id=current_user.id, status="pending"
    ).count()

    suggested_friends = _suggested_friends(current_user.id, limit=5)
    suggested_pages = _suggested_pages(current_user.id, limit=4)
    suggested_groups = _suggested_groups(current_user.id, limit=4)

    return render_template(
        "feed/home.html",
        ranked=ranked,
        posts=posts,
        page=page,
        has_next=len(ranked) >= 15,
        unread_notif=unread_notif,
        pending_requests=pending_requests,
        suggested_friends=suggested_friends,
        suggested_pages=suggested_pages,
        suggested_groups=suggested_groups,
    )


@bp.route("/feed/more")
@login_required
def more():
    """AJAX pagination: returns rendered HTML for next page."""
    page = max(1, int(request.args.get("page", 2)))
    ranked = build_feed_for_user(current_user, page=page)
    posts = [r[0] for r in ranked]
    if posts:
        for p in posts:
            db.session.add(PostView(post_id=p.id, user_id=current_user.id))
        db.session.commit()
    return render_template("feed/_post_list.html", ranked=ranked, posts=posts)


@bp.route("/saved")
@login_required
def saved():
    saves = db.session.query(Save).filter_by(user_id=current_user.id).order_by(Save.created_at.desc()).all()
    posts = [s.post for s in saves if s.post and not s.post.is_deleted]
    return render_template("feed/saved.html", posts=posts)


@bp.route("/search")
@login_required
def search():
    q = (request.args.get("q") or "").strip()
    results = {"users": [], "pages": [], "groups": [], "posts": []}
    if q:
        like = f"%{q}%"
        results["users"] = db.session.query(User).filter(
            or_(User.full_name.ilike(like), User.username.ilike(like))
        ).limit(20).all()
        results["pages"] = db.session.query(Page).filter(Page.name.ilike(like)).limit(20).all()
        results["groups"] = db.session.query(Group).filter(Group.name.ilike(like)).limit(20).all()
        results["posts"] = db.session.query(Post).filter(
            Post.is_deleted.is_(False),
            Post.content.ilike(like),
            or_(Post.visibility == "public", Post.author_id == current_user.id),
        ).order_by(Post.created_at.desc()).limit(20).all()
    return render_template("feed/search.html", q=q, results=results)


def _suggested_friends(user_id, limit=5):
    """Users who are friends of your friends but not you, ranked by mutual count."""
    u = db.session.get(User, user_id)
    friend_ids = set(u.friends_ids())
    if not friend_ids:
        # Fall back to any active users
        return db.session.query(User).filter(
            User.id != user_id, User.is_active_user.is_(True)
        ).order_by(func.random()).limit(limit).all()

    fof_rows = db.session.query(Friendship).filter(
        Friendship.status == "accepted",
        or_(Friendship.user_id.in_(friend_ids), Friendship.friend_id.in_(friend_ids)),
    ).all()
    candidates = {}
    for r in fof_rows:
        for uid in (r.user_id, r.friend_id):
            if uid == user_id or uid in friend_ids:
                continue
            candidates[uid] = candidates.get(uid, 0) + 1
    # Exclude users with existing friend requests either direction
    existing = db.session.query(Friendship).filter(
        or_(Friendship.user_id == user_id, Friendship.friend_id == user_id)
    ).all()
    for r in existing:
        other = r.friend_id if r.user_id == user_id else r.user_id
        candidates.pop(other, None)

    top_ids = sorted(candidates, key=candidates.get, reverse=True)[:limit]
    users = db.session.query(User).filter(User.id.in_(top_ids)).all() if top_ids else []
    order = {uid: i for i, uid in enumerate(top_ids)}
    users.sort(key=lambda u: order.get(u.id, 999))
    return users


def _suggested_pages(user_id, limit=4):
    followed = db.session.query(PageFollow.page_id).filter_by(user_id=user_id).all()
    followed_ids = [r[0] for r in followed]
    q = db.session.query(Page)
    if followed_ids:
        q = q.filter(~Page.id.in_(followed_ids))
    return q.order_by(func.random()).limit(limit).all()


def _suggested_groups(user_id, limit=4):
    from ..models import GroupMember
    member = db.session.query(GroupMember.group_id).filter_by(user_id=user_id).all()
    member_ids = [r[0] for r in member]
    q = db.session.query(Group).filter(Group.privacy == "public")
    if member_ids:
        q = q.filter(~Group.id.in_(member_ids))
    return q.order_by(func.random()).limit(limit).all()
