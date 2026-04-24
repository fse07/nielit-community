"""Admin dashboard and moderation."""
from functools import wraps
from flask import Blueprint, render_template, request, redirect, url_for, flash, abort, current_app
from flask_login import login_required, current_user
from sqlalchemy import func

from ..extensions import db
from ..models import User, Post, PostMedia, Report, Notification
from ..utils.uploads import save_image
from ..utils.link_preview import fetch_link_preview

bp = Blueprint("admin", __name__)


def admin_required(fn):
    @wraps(fn)
    @login_required
    def wrapper(*args, **kwargs):
        if not current_user.is_admin:
            abort(403)
        return fn(*args, **kwargs)
    return wrapper


@bp.route("/")
@admin_required
def dashboard():
    stats = {
        "users": db.session.query(func.count(User.id)).scalar(),
        "posts": db.session.query(func.count(Post.id)).filter_by(is_deleted=False).scalar(),
        "deleted_posts": db.session.query(func.count(Post.id)).filter_by(is_deleted=True).scalar(),
        "reports_open": db.session.query(func.count(Report.id)).filter_by(status="open").scalar(),
        "sponsored": db.session.query(func.count(Post.id)).filter_by(is_sponsored=True, is_deleted=False).scalar(),
    }
    recent_users = db.session.query(User).order_by(User.created_at.desc()).limit(10).all()
    recent_posts = db.session.query(Post).order_by(Post.created_at.desc()).limit(10).all()
    open_reports = db.session.query(Report).filter_by(status="open").order_by(Report.created_at.desc()).limit(10).all()
    return render_template("admin/dashboard.html",
                           stats=stats, recent_users=recent_users,
                           recent_posts=recent_posts, open_reports=open_reports)


@bp.route("/users")
@admin_required
def users():
    page = max(1, int(request.args.get("page", 1)))
    per_page = 50
    q = db.session.query(User).order_by(User.created_at.desc())
    total = q.count()
    users_list = q.limit(per_page).offset((page - 1) * per_page).all()
    return render_template("admin/users.html", users=users_list, page=page, per_page=per_page, total=total)


@bp.route("/users/<int:user_id>/toggle-active", methods=["POST"])
@admin_required
def toggle_active(user_id):
    u = db.session.get(User, user_id)
    if not u:
        abort(404)
    if u.is_admin and u.id != current_user.id:
        flash("Cannot disable another admin.", "warning")
    else:
        u.is_active_user = not u.is_active_user
        db.session.commit()
        flash(f"User '{u.username}' is now {'active' if u.is_active_user else 'disabled'}.", "info")
    return redirect(url_for("admin.users"))


@bp.route("/users/<int:user_id>/promote", methods=["POST"])
@admin_required
def promote(user_id):
    u = db.session.get(User, user_id)
    if not u:
        abort(404)
    u.is_admin = not u.is_admin
    db.session.commit()
    flash(f"User '{u.username}' admin status: {u.is_admin}", "info")
    return redirect(url_for("admin.users"))


@bp.route("/posts")
@admin_required
def posts():
    page = max(1, int(request.args.get("page", 1)))
    per_page = 30
    show_deleted = request.args.get("show_deleted") == "1"
    q = db.session.query(Post).order_by(Post.created_at.desc())
    if not show_deleted:
        q = q.filter_by(is_deleted=False)
    total = q.count()
    items = q.limit(per_page).offset((page - 1) * per_page).all()
    return render_template("admin/posts.html", posts=items, page=page, per_page=per_page, total=total, show_deleted=show_deleted)


@bp.route("/posts/<int:post_id>/delete", methods=["POST"])
@admin_required
def delete_post(post_id):
    p = db.session.get(Post, post_id)
    if not p:
        abort(404)
    p.is_deleted = True
    db.session.commit()
    flash("Post removed.", "info")
    return redirect(request.referrer or url_for("admin.posts"))


@bp.route("/posts/<int:post_id>/restore", methods=["POST"])
@admin_required
def restore_post(post_id):
    p = db.session.get(Post, post_id)
    if not p:
        abort(404)
    p.is_deleted = False
    db.session.commit()
    flash("Post restored.", "info")
    return redirect(request.referrer or url_for("admin.posts"))


@bp.route("/sponsored/new", methods=["GET", "POST"])
@admin_required
def new_sponsored():
    if request.method == "POST":
        content = (request.form.get("content") or "").strip()
        link_url = (request.form.get("link_url") or "").strip()
        if not content and not link_url:
            flash("Need at least content or a link.", "danger")
            return redirect(url_for("admin.new_sponsored"))

        media_file = request.files.get("media")
        media_fn = ""
        if media_file and media_file.filename:
            try:
                media_fn = save_image(media_file)
            except Exception as e:
                flash(f"Image upload failed: {e}", "warning")

        post_type = "photo" if media_fn else ("link" if link_url else "text")

        p = Post(
            author_id=current_user.id,
            content=content,
            post_type=post_type,
            visibility="public",
            is_sponsored=True,
            link_url=link_url,
        )
        if link_url:
            preview = fetch_link_preview(link_url)
            p.link_title = preview.get("title", "")
            p.link_description = preview.get("description", "")
            p.link_image = preview.get("image", "")

        db.session.add(p)
        db.session.flush()
        if media_fn:
            db.session.add(PostMedia(post_id=p.id, media_type="image", filename=media_fn))
        db.session.commit()
        flash("Sponsored post created.", "success")
        return redirect(url_for("admin.dashboard"))
    return render_template("admin/new_sponsored.html")


@bp.route("/reports")
@admin_required
def reports():
    items = db.session.query(Report).order_by(Report.created_at.desc()).limit(100).all()
    return render_template("admin/reports.html", reports=items)


@bp.route("/reports/<int:rid>/resolve", methods=["POST"])
@admin_required
def resolve_report(rid):
    r = db.session.get(Report, rid)
    if not r:
        abort(404)
    r.status = request.form.get("action", "resolved")
    db.session.commit()
    return redirect(url_for("admin.reports"))
