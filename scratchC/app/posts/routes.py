"""Post CRUD and view routes."""
from datetime import datetime, timedelta
from flask import Blueprint, render_template, request, redirect, url_for, flash, abort, jsonify, current_app
from flask_login import login_required, current_user
from sqlalchemy import func

from ..extensions import db
from ..models import (
    Post, PostMedia, Poll, PollOption, PollVote, Page, Group, GroupMember,
    Reaction, Comment, Save, PostView, Notification, User,
)
from ..utils.uploads import save_image, save_video
from ..utils.link_preview import fetch_link_preview
from ..feed.ranking import record_interaction

bp = Blueprint("posts", __name__)


VALID_VISIBILITY = {"public", "friends", "friends_of_friends", "only_me"}
VALID_POST_TYPES = {"text", "photo", "album", "video", "short_video", "link", "poll", "shared", "event"}


def _post_can_be_seen_by(post, user):
    """Hard visibility check at view time."""
    if post.is_deleted:
        return False
    if post.author_id == user.id:
        return True
    if post.is_sponsored:
        return True
    if post.group_id:
        return user.is_member_of_group(post.group_id) or post.visibility == "public"
    if post.page_id:
        return True  # page posts are effectively public to followers + anyone
    if post.visibility == "public":
        return True
    if post.visibility == "only_me":
        return False
    friend_ids = set(user.friends_ids())
    if post.visibility == "friends":
        return post.author_id in friend_ids
    if post.visibility == "friends_of_friends":
        if post.author_id in friend_ids:
            return True
        # FoF check
        author = db.session.get(User, post.author_id)
        if not author:
            return False
        author_friends = set(author.friends_ids())
        return bool(friend_ids & author_friends)
    return False


@bp.route("/new", methods=["GET", "POST"])
@login_required
def create():
    if request.method == "GET":
        return render_template("posts/create.html",
                               pages=current_user.owned_pages,
                               groups=[gm.group for gm in current_user.group_memberships])

    # POST - create post
    content = (request.form.get("content") or "").strip()
    visibility = request.form.get("visibility", "friends")
    if visibility not in VALID_VISIBILITY:
        visibility = "friends"

    feeling = (request.form.get("feeling") or "").strip()[:60]
    activity = (request.form.get("activity") or "").strip()[:60]
    location = (request.form.get("location") or "").strip()[:200]
    link_url = (request.form.get("link_url") or "").strip()[:500]

    target_kind = request.form.get("target_kind", "profile")  # profile, page, group
    target_id = request.form.get("target_id")
    page_id = None
    group_id = None

    if target_kind == "page" and target_id:
        p = db.session.get(Page, int(target_id))
        if p and p.owner_id == current_user.id:
            page_id = p.id
    elif target_kind == "group" and target_id:
        g = db.session.get(Group, int(target_id))
        if g and current_user.is_member_of_group(g.id):
            group_id = g.id
            visibility = "public"  # group posts ignore friend visibility

    # Handle media uploads
    media_files = request.files.getlist("media")
    media_files = [m for m in media_files if m and m.filename]

    images_saved = []
    videos_saved = []
    for f in media_files[:10]:
        ext = f.filename.rsplit(".", 1)[-1].lower()
        if ext in current_app.config["ALLOWED_IMAGE_EXTENSIONS"]:
            try:
                images_saved.append(save_image(f))
            except Exception as e:
                flash(f"Image upload failed: {e}", "warning")
        elif ext in current_app.config["ALLOWED_VIDEO_EXTENSIONS"]:
            try:
                videos_saved.append(save_video(f))
            except Exception as e:
                flash(f"Video upload failed: {e}", "warning")

    # Determine post type
    post_type = "text"
    is_poll = bool(request.form.get("poll_question"))
    poll_opts_raw = [o.strip() for o in request.form.getlist("poll_options") if o.strip()]

    if videos_saved:
        post_type = "short_video" if request.form.get("short_video") else "video"
    elif len(images_saved) > 1:
        post_type = "album"
    elif len(images_saved) == 1:
        post_type = "photo"
    elif is_poll and len(poll_opts_raw) >= 2:
        post_type = "poll"
    elif link_url:
        post_type = "link"

    if not content and not images_saved and not videos_saved and not is_poll and not link_url:
        flash("Your post is empty. Add some text, media, a link, or a poll.", "danger")
        return redirect(url_for("posts.create"))

    post = Post(
        author_id=current_user.id,
        page_id=page_id,
        group_id=group_id,
        content=content,
        post_type=post_type,
        visibility=visibility,
        location=location,
        feeling=feeling,
        activity=activity,
        link_url=link_url,
    )

    # Fetch link preview
    if link_url:
        preview = fetch_link_preview(link_url)
        post.link_title = preview.get("title", "")
        post.link_description = preview.get("description", "")
        post.link_image = preview.get("image", "")

    db.session.add(post)
    db.session.flush()  # get post.id

    # Attach media
    for i, fn in enumerate(images_saved):
        db.session.add(PostMedia(post_id=post.id, media_type="image", filename=fn, order_index=i))
    for i, fn in enumerate(videos_saved):
        db.session.add(PostMedia(post_id=post.id, media_type="video", filename=fn, order_index=i))

    # Attach poll
    if post_type == "poll":
        poll = Poll(
            post_id=post.id,
            question=request.form.get("poll_question", "")[:500],
            multi_choice=bool(request.form.get("poll_multi")),
        )
        db.session.add(poll)
        db.session.flush()
        for opt_text in poll_opts_raw[:8]:
            db.session.add(PollOption(poll_id=poll.id, text=opt_text[:200]))

    db.session.commit()
    flash("Your post is live!", "success")
    return redirect(url_for("feed.home"))


@bp.route("/<int:post_id>")
@login_required
def detail(post_id):
    post = db.session.get(Post, post_id)
    if not post or not _post_can_be_seen_by(post, current_user):
        abort(404)
    # Record view
    db.session.add(PostView(post_id=post.id, user_id=current_user.id))
    post.view_count = (post.view_count or 0) + 1
    db.session.commit()
    record_interaction(current_user.id, post, "view")

    comments = db.session.query(Comment).filter_by(post_id=post.id, parent_id=None).order_by(Comment.created_at.asc()).all()
    return render_template("posts/detail.html", post=post, comments=comments)


@bp.route("/<int:post_id>/delete", methods=["POST"])
@login_required
def delete(post_id):
    post = db.session.get(Post, post_id)
    if not post:
        abort(404)
    if post.author_id != current_user.id and not current_user.is_admin:
        abort(403)
    post.is_deleted = True
    db.session.commit()
    flash("Post deleted.", "info")
    return redirect(request.referrer or url_for("feed.home"))


@bp.route("/<int:post_id>/share", methods=["POST"])
@login_required
def share(post_id):
    original = db.session.get(Post, post_id)
    if not original or not _post_can_be_seen_by(original, current_user):
        abort(404)
    share_text = (request.form.get("content") or "").strip()
    visibility = request.form.get("visibility", "friends")
    if visibility not in VALID_VISIBILITY:
        visibility = "friends"

    new_post = Post(
        author_id=current_user.id,
        content=share_text,
        post_type="shared",
        visibility=visibility,
        shared_post_id=original.id,
    )
    original.share_count = (original.share_count or 0) + 1

    db.session.add(new_post)
    db.session.flush()
    record_interaction(current_user.id, original, "share")

    # Notify original author
    if original.author_id != current_user.id:
        db.session.add(Notification(
            user_id=original.author_id,
            actor_id=current_user.id,
            notif_type="shared",
            post_id=original.id,
            content=f"{current_user.full_name} shared your post",
        ))
    db.session.commit()
    flash("Post shared to your feed.", "success")
    return redirect(url_for("feed.home"))


@bp.route("/<int:post_id>/insights")
@login_required
def insights(post_id):
    post = db.session.get(Post, post_id)
    if not post:
        abort(404)
    # Only author, page owner, or admin can view insights
    can_view = post.author_id == current_user.id or current_user.is_admin
    if post.page_id and not can_view:
        p = db.session.get(Page, post.page_id)
        if p and p.owner_id == current_user.id:
            can_view = True
    if not can_view:
        abort(403)

    total_views = post.view_count
    unique_viewers = db.session.query(func.count(func.distinct(PostView.user_id))).filter_by(post_id=post.id).scalar()
    reaction_breakdown = post.reaction_breakdown()
    total_watch = post.total_watch_seconds
    hourly_views = _hourly_breakdown(post.id)
    saves = db.session.query(func.count(Save.id)).filter_by(post_id=post.id).scalar()

    return render_template(
        "posts/insights.html",
        post=post,
        total_views=total_views,
        unique_viewers=unique_viewers,
        reactions=reaction_breakdown,
        total_watch=total_watch,
        hourly_views=hourly_views,
        saves=saves,
    )


def _hourly_breakdown(post_id, hours=24):
    """Return list of (hour_bucket, count) for last N hours. DB-agnostic."""
    since = datetime.utcnow() - timedelta(hours=hours)
    rows = db.session.query(PostView.created_at).filter(
        PostView.post_id == post_id, PostView.created_at >= since
    ).all()
    buckets = {}
    for (ts,) in rows:
        if ts is None:
            continue
        key = ts.strftime('%m-%d %H:00')
        buckets[key] = buckets.get(key, 0) + 1
    return sorted(buckets.items())


@bp.route("/poll/<int:poll_id>/vote", methods=["POST"])
@login_required
def vote_poll(poll_id):
    poll = db.session.get(Poll, poll_id)
    if not poll:
        abort(404)
    if poll.is_closed():
        flash("This poll is closed.", "warning")
        return redirect(request.referrer or url_for("feed.home"))

    option_ids = request.form.getlist("option_id")
    if not option_ids:
        return redirect(request.referrer or url_for("feed.home"))
    option_ids = [int(x) for x in option_ids]
    if not poll.multi_choice:
        option_ids = option_ids[:1]

    # Remove existing votes if re-voting
    db.session.query(PollVote).filter_by(poll_id=poll.id, user_id=current_user.id).delete()
    for oid in option_ids:
        opt = db.session.get(PollOption, oid)
        if opt and opt.poll_id == poll.id:
            db.session.add(PollVote(poll_id=poll.id, option_id=oid, user_id=current_user.id))
    db.session.commit()
    record_interaction(current_user.id, poll.post, "reaction")
    return redirect(request.referrer or url_for("feed.home"))
