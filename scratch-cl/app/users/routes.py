"""User profile and friendship routes."""
from datetime import datetime
from flask import Blueprint, render_template, request, redirect, url_for, flash, abort, jsonify
from flask_login import login_required, current_user
from sqlalchemy import or_, and_

from ..extensions import db
from ..models import User, Friendship, Post, Notification
from ..utils.uploads import save_avatar, save_image
from ..posts.routes import _post_can_be_seen_by

bp = Blueprint("users", __name__)


@bp.route("/<username>")
@login_required
def profile(username):
    user = db.session.query(User).filter_by(username=username).first()
    if not user:
        abort(404)

    rel = current_user.friend_request_status_with(user.id)
    is_self = user.id == current_user.id

    # Fetch user's posts visible to viewer
    all_posts = db.session.query(Post).filter_by(author_id=user.id, is_deleted=False).order_by(Post.created_at.desc()).limit(50).all()
    visible_posts = [p for p in all_posts if _post_can_be_seen_by(p, current_user)]

    friend_count = len(user.friends_ids())
    friends = db.session.query(User).filter(User.id.in_(user.friends_ids())).limit(9).all() if friend_count else []

    return render_template(
        "users/profile.html",
        user=user,
        rel=rel,
        is_self=is_self,
        posts=visible_posts,
        friend_count=friend_count,
        friends=friends,
    )


@bp.route("/<username>/friends")
@login_required
def friends(username):
    user = db.session.query(User).filter_by(username=username).first()
    if not user:
        abort(404)
    friends = db.session.query(User).filter(User.id.in_(user.friends_ids())).all() if user.friends_ids() else []
    return render_template("users/friends.html", user=user, friends=friends)


@bp.route("/friend-request", methods=["POST"])
@login_required
def friend_request():
    target_id = int(request.form.get("user_id", 0))
    if target_id == current_user.id:
        return jsonify({"ok": False, "error": "self"}), 400
    target = db.session.get(User, target_id)
    if not target:
        abort(404)

    existing = db.session.query(Friendship).filter(
        or_(
            and_(Friendship.user_id == current_user.id, Friendship.friend_id == target_id),
            and_(Friendship.user_id == target_id, Friendship.friend_id == current_user.id),
        )
    ).first()

    if existing:
        return jsonify({"ok": False, "error": "exists", "status": existing.status})

    fr = Friendship(user_id=current_user.id, friend_id=target_id, status="pending")
    db.session.add(fr)
    db.session.add(Notification(
        user_id=target_id,
        actor_id=current_user.id,
        notif_type="friend_request",
        content=f"{current_user.full_name} sent you a friend request",
    ))
    db.session.commit()
    return jsonify({"ok": True, "status": "pending_out"})


@bp.route("/friend-accept", methods=["POST"])
@login_required
def friend_accept():
    other_id = int(request.form.get("user_id", 0))
    fr = db.session.query(Friendship).filter_by(
        user_id=other_id, friend_id=current_user.id, status="pending"
    ).first()
    if not fr:
        return jsonify({"ok": False}), 404
    fr.status = "accepted"
    fr.accepted_at = datetime.utcnow()
    db.session.add(Notification(
        user_id=other_id,
        actor_id=current_user.id,
        notif_type="friend_accept",
        content=f"{current_user.full_name} accepted your friend request",
    ))
    db.session.commit()
    return jsonify({"ok": True, "status": "accepted"})


@bp.route("/friend-reject", methods=["POST"])
@login_required
def friend_reject():
    other_id = int(request.form.get("user_id", 0))
    fr = db.session.query(Friendship).filter(
        or_(
            and_(Friendship.user_id == other_id, Friendship.friend_id == current_user.id),
            and_(Friendship.user_id == current_user.id, Friendship.friend_id == other_id),
        )
    ).first()
    if fr:
        db.session.delete(fr)
        db.session.commit()
    return jsonify({"ok": True, "status": "none"})


@bp.route("/friend-requests")
@login_required
def friend_requests():
    pending_in = db.session.query(Friendship).filter_by(friend_id=current_user.id, status="pending").all()
    pending_out = db.session.query(Friendship).filter_by(user_id=current_user.id, status="pending").all()
    return render_template("users/friend_requests.html", pending_in=pending_in, pending_out=pending_out)


@bp.route("/notifications")
@login_required
def notifications_page():
    notifs = db.session.query(Notification).filter_by(user_id=current_user.id).order_by(Notification.created_at.desc()).limit(100).all()
    db.session.query(Notification).filter_by(user_id=current_user.id, is_read=False).update({"is_read": True})
    db.session.commit()
    return render_template("users/notifications.html", notifs=notifs)


@bp.route("/settings", methods=["GET", "POST"])
@login_required
def settings():
    if request.method == "POST":
        current_user.full_name = (request.form.get("full_name") or current_user.full_name).strip()[:120]
        current_user.bio = (request.form.get("bio") or "").strip()[:500]
        current_user.location = (request.form.get("location") or "").strip()[:120]

        avatar_file = request.files.get("avatar")
        if avatar_file and avatar_file.filename:
            try:
                current_user.avatar = save_avatar(avatar_file)
            except Exception as e:
                flash(f"Avatar upload failed: {e}", "warning")

        cover_file = request.files.get("cover")
        if cover_file and cover_file.filename:
            try:
                current_user.cover = save_image(cover_file, subdir="images", max_dim=1800)
            except Exception as e:
                flash(f"Cover upload failed: {e}", "warning")

        # Password change
        new_pw = request.form.get("new_password")
        if new_pw:
            current_pw = request.form.get("current_password", "")
            if not current_user.check_password(current_pw):
                flash("Current password incorrect.", "danger")
            elif len(new_pw) < 8:
                flash("New password must be at least 8 characters.", "danger")
            else:
                current_user.set_password(new_pw)
                flash("Password updated.", "success")

        db.session.commit()
        flash("Profile updated.", "success")
        return redirect(url_for("users.settings"))

    return render_template("users/settings.html")
