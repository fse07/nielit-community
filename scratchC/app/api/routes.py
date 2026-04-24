"""JSON AJAX endpoints used by the frontend."""
from flask import Blueprint, request, jsonify, abort, render_template_string
from flask_login import login_required, current_user

from ..extensions import db, csrf
from ..models import Post, Reaction, Comment, Save, PostView, Notification
from ..feed.ranking import record_interaction
from ..posts.routes import _post_can_be_seen_by

bp = Blueprint("api", __name__)


VALID_REACTIONS = {"like", "love", "haha", "wow", "sad", "angry"}


@bp.route("/react", methods=["POST"])
@login_required
def react():
    post_id = int(request.form.get("post_id", 0))
    rtype = request.form.get("type", "like")
    if rtype not in VALID_REACTIONS:
        rtype = "like"
    post = db.session.get(Post, post_id)
    if not post or not _post_can_be_seen_by(post, current_user):
        return jsonify({"error": "not found"}), 404

    existing = db.session.query(Reaction).filter_by(post_id=post.id, user_id=current_user.id).first()
    removed = False
    changed = False
    if existing:
        if existing.reaction_type == rtype:
            # Toggle off
            db.session.delete(existing)
            post.reaction_count = max(0, (post.reaction_count or 0) - 1)
            removed = True
        else:
            existing.reaction_type = rtype
            changed = True
    else:
        db.session.add(Reaction(post_id=post.id, user_id=current_user.id, reaction_type=rtype))
        post.reaction_count = (post.reaction_count or 0) + 1

    db.session.commit()
    if not removed:
        record_interaction(current_user.id, post, "reaction")
        # Notify author (only on add / change, not on remove, not on self)
        if post.author_id != current_user.id:
            db.session.add(Notification(
                user_id=post.author_id,
                actor_id=current_user.id,
                notif_type="reacted",
                post_id=post.id,
                content=f"{current_user.full_name} reacted {rtype} to your post",
            ))
            db.session.commit()

    return jsonify({
        "ok": True,
        "removed": removed,
        "changed": changed,
        "reaction_type": None if removed else rtype,
        "reaction_count": post.reaction_count,
        "breakdown": post.reaction_breakdown(),
    })


@bp.route("/comment", methods=["POST"])
@login_required
def comment():
    post_id = int(request.form.get("post_id", 0))
    content = (request.form.get("content") or "").strip()
    parent_id = request.form.get("parent_id")
    parent_id = int(parent_id) if parent_id else None

    if not content:
        return jsonify({"error": "empty"}), 400
    post = db.session.get(Post, post_id)
    if not post or not _post_can_be_seen_by(post, current_user):
        return jsonify({"error": "not found"}), 404

    c = Comment(post_id=post.id, user_id=current_user.id, content=content[:2000], parent_id=parent_id)
    db.session.add(c)
    post.comment_count = (post.comment_count or 0) + 1
    db.session.flush()
    record_interaction(current_user.id, post, "comment")

    if post.author_id != current_user.id:
        db.session.add(Notification(
            user_id=post.author_id,
            actor_id=current_user.id,
            notif_type="commented",
            post_id=post.id,
            comment_id=c.id,
            content=f"{current_user.full_name} commented on your post",
        ))
    db.session.commit()

    html = render_template_string(
        """
        <div class="comment" id="comment-{{ c.id }}">
          <div class="avatar-sm">
            {% if c.author.avatar %}<img src="{{ c.author.avatar_url() }}" alt="">{% else %}<span>{{ c.author.initials() }}</span>{% endif %}
          </div>
          <div class="comment-body">
            <a class="comment-author" href="{{ url_for('users.profile', username=c.author.username) }}">{{ c.author.full_name }}</a>
            <span class="comment-text">{{ c.content }}</span>
            <div class="comment-meta">{{ c.created_at|timeago }}</div>
          </div>
        </div>
        """, c=c
    )
    return jsonify({
        "ok": True,
        "html": html,
        "comment_count": post.comment_count,
    })


@bp.route("/save", methods=["POST"])
@login_required
def save_toggle():
    post_id = int(request.form.get("post_id", 0))
    post = db.session.get(Post, post_id)
    if not post or not _post_can_be_seen_by(post, current_user):
        return jsonify({"error": "not found"}), 404

    existing = db.session.query(Save).filter_by(post_id=post.id, user_id=current_user.id).first()
    if existing:
        db.session.delete(existing)
        saved = False
    else:
        db.session.add(Save(post_id=post.id, user_id=current_user.id))
        saved = True
        record_interaction(current_user.id, post, "save")
    db.session.commit()
    return jsonify({"ok": True, "saved": saved})


@bp.route("/view-metrics", methods=["POST"])
@login_required
def view_metrics():
    """
    Browser posts dwell time / video watch seconds when user scrolls away from a post.
    Used for ranking signal.
    """
    post_id = int(request.form.get("post_id", 0))
    dwell_ms = int(request.form.get("dwell_ms", 0))
    watch_seconds = int(request.form.get("watch_seconds", 0))
    post = db.session.get(Post, post_id)
    if not post:
        return jsonify({"ok": False}), 404

    # Update latest view record
    pv = db.session.query(PostView).filter_by(post_id=post.id, user_id=current_user.id).order_by(PostView.created_at.desc()).first()
    if pv:
        pv.dwell_ms = max(pv.dwell_ms, dwell_ms)
        pv.watch_seconds = max(pv.watch_seconds, watch_seconds)
    post.total_watch_seconds = (post.total_watch_seconds or 0) + watch_seconds
    db.session.commit()

    if dwell_ms > 3000:
        record_interaction(current_user.id, post, "dwell_long")
    if watch_seconds > 15:
        record_interaction(current_user.id, post, "watch_long")

    return jsonify({"ok": True})


@bp.route("/notifications")
@login_required
def notifications():
    notifs = db.session.query(Notification).filter_by(user_id=current_user.id).order_by(Notification.created_at.desc()).limit(30).all()
    unread = [n for n in notifs if not n.is_read]
    items = [{
        "id": n.id,
        "type": n.notif_type,
        "content": n.content,
        "post_id": n.post_id,
        "created_at": n.created_at.isoformat(),
        "is_read": n.is_read,
    } for n in notifs]
    return jsonify({"ok": True, "items": items, "unread_count": len(unread)})


@bp.route("/notifications/mark-read", methods=["POST"])
@login_required
def mark_notifs_read():
    db.session.query(Notification).filter_by(user_id=current_user.id, is_read=False).update({"is_read": True})
    db.session.commit()
    return jsonify({"ok": True})
