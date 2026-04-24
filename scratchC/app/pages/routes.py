"""Pages (creator/business pages) blueprint."""
from flask import Blueprint, render_template, request, redirect, url_for, flash, abort
from flask_login import login_required, current_user

from ..extensions import db
from ..models import Page, PageFollow, Post
from ..utils.slugify import unique_slug
from ..utils.uploads import save_image

bp = Blueprint("pages", __name__)


@bp.route("/")
@login_required
def index():
    followed_ids = [f.page_id for f in db.session.query(PageFollow).filter_by(user_id=current_user.id).all()]
    followed = db.session.query(Page).filter(Page.id.in_(followed_ids)).all() if followed_ids else []
    my_pages = db.session.query(Page).filter_by(owner_id=current_user.id).all()
    discover = db.session.query(Page).filter(
        ~Page.id.in_([p.id for p in followed + my_pages]) if (followed or my_pages) else True
    ).limit(30).all()
    return render_template("pages/index.html", followed=followed, my_pages=my_pages, discover=discover)


@bp.route("/new", methods=["GET", "POST"])
@login_required
def create():
    if request.method == "POST":
        name = (request.form.get("name") or "").strip()[:120]
        description = (request.form.get("description") or "").strip()[:2000]
        category = (request.form.get("category") or "General").strip()[:60]
        if not name:
            flash("Page name required.", "danger")
            return redirect(url_for("pages.create"))

        slug = unique_slug(name, lambda s: db.session.query(Page).filter_by(slug=s).first() is not None)

        avatar_fn = ""
        cover_fn = ""
        if request.files.get("avatar") and request.files["avatar"].filename:
            try:
                avatar_fn = save_image(request.files["avatar"], max_dim=800)
            except Exception:
                pass
        if request.files.get("cover") and request.files["cover"].filename:
            try:
                cover_fn = save_image(request.files["cover"])
            except Exception:
                pass

        p = Page(name=name, slug=slug, description=description, category=category,
                 avatar=avatar_fn, cover=cover_fn, owner_id=current_user.id)
        db.session.add(p)
        db.session.flush()
        db.session.add(PageFollow(user_id=current_user.id, page_id=p.id))
        db.session.commit()
        flash(f"Page '{name}' created.", "success")
        return redirect(url_for("pages.detail", slug=slug))
    return render_template("pages/create.html")


@bp.route("/<slug>")
@login_required
def detail(slug):
    p = db.session.query(Page).filter_by(slug=slug).first()
    if not p:
        abort(404)
    is_follower = current_user.follows_page(p.id)
    is_owner = p.owner_id == current_user.id
    posts = db.session.query(Post).filter_by(page_id=p.id, is_deleted=False).order_by(Post.created_at.desc()).limit(40).all()
    return render_template("pages/detail.html", page=p, is_follower=is_follower, is_owner=is_owner, posts=posts)


@bp.route("/<slug>/follow", methods=["POST"])
@login_required
def follow(slug):
    p = db.session.query(Page).filter_by(slug=slug).first()
    if not p:
        abort(404)
    if not current_user.follows_page(p.id):
        db.session.add(PageFollow(user_id=current_user.id, page_id=p.id))
        db.session.commit()
    return redirect(url_for("pages.detail", slug=slug))


@bp.route("/<slug>/unfollow", methods=["POST"])
@login_required
def unfollow(slug):
    p = db.session.query(Page).filter_by(slug=slug).first()
    if not p:
        abort(404)
    f = db.session.query(PageFollow).filter_by(user_id=current_user.id, page_id=p.id).first()
    if f:
        db.session.delete(f)
        db.session.commit()
    return redirect(url_for("pages.detail", slug=slug))
