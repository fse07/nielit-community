"""Groups blueprint."""
from flask import Blueprint, render_template, request, redirect, url_for, flash, abort, jsonify
from flask_login import login_required, current_user
from sqlalchemy import func

from ..extensions import db
from ..models import Group, GroupMember, Post
from ..utils.slugify import unique_slug
from ..utils.uploads import save_image

bp = Blueprint("groups", __name__)


@bp.route("/")
@login_required
def index():
    my_groups = db.session.query(Group).join(GroupMember).filter(GroupMember.user_id == current_user.id).all()
    discover = db.session.query(Group).filter(
        Group.privacy == "public",
        ~Group.id.in_([g.id for g in my_groups]) if my_groups else True
    ).order_by(Group.created_at.desc()).limit(30).all()
    return render_template("groups/index.html", my_groups=my_groups, discover=discover)


@bp.route("/new", methods=["GET", "POST"])
@login_required
def create():
    if request.method == "POST":
        name = (request.form.get("name") or "").strip()[:120]
        description = (request.form.get("description") or "").strip()[:2000]
        privacy = request.form.get("privacy", "public")
        if privacy not in ("public", "private"):
            privacy = "public"
        if not name:
            flash("Group name required.", "danger")
            return redirect(url_for("groups.create"))

        slug = unique_slug(name, lambda s: db.session.query(Group).filter_by(slug=s).first() is not None)

        cover_file = request.files.get("cover")
        cover_fn = ""
        if cover_file and cover_file.filename:
            try:
                cover_fn = save_image(cover_file)
            except Exception as e:
                flash(f"Cover upload failed: {e}", "warning")

        g = Group(name=name, slug=slug, description=description, privacy=privacy,
                  cover=cover_fn, created_by=current_user.id)
        db.session.add(g)
        db.session.flush()
        db.session.add(GroupMember(group_id=g.id, user_id=current_user.id, role="admin"))
        db.session.commit()
        flash(f"Group '{name}' created.", "success")
        return redirect(url_for("groups.detail", slug=slug))
    return render_template("groups/create.html")


@bp.route("/<slug>")
@login_required
def detail(slug):
    g = db.session.query(Group).filter_by(slug=slug).first()
    if not g:
        abort(404)
    is_member = current_user.is_member_of_group(g.id)
    posts = []
    if is_member or g.privacy == "public":
        posts = db.session.query(Post).filter_by(group_id=g.id, is_deleted=False).order_by(Post.created_at.desc()).limit(40).all()
    members = [m.user for m in g.members[:12]]
    return render_template("groups/detail.html", group=g, is_member=is_member, posts=posts, members=members)


@bp.route("/<slug>/join", methods=["POST"])
@login_required
def join(slug):
    g = db.session.query(Group).filter_by(slug=slug).first()
    if not g:
        abort(404)
    if not current_user.is_member_of_group(g.id):
        db.session.add(GroupMember(group_id=g.id, user_id=current_user.id, role="member"))
        db.session.commit()
        flash(f"Joined '{g.name}'.", "success")
    return redirect(url_for("groups.detail", slug=slug))


@bp.route("/<slug>/leave", methods=["POST"])
@login_required
def leave(slug):
    g = db.session.query(Group).filter_by(slug=slug).first()
    if not g:
        abort(404)
    m = db.session.query(GroupMember).filter_by(group_id=g.id, user_id=current_user.id).first()
    if m:
        db.session.delete(m)
        db.session.commit()
        flash(f"Left '{g.name}'.", "info")
    return redirect(url_for("groups.index"))
