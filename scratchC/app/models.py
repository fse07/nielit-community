"""Database models."""
from datetime import datetime, timedelta
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import UserMixin
from sqlalchemy import Index, UniqueConstraint, func, and_, or_
from sqlalchemy.orm import relationship

from .extensions import db


# ---------- USERS & SOCIAL GRAPH ----------

class User(UserMixin, db.Model):
    __tablename__ = "users"
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    username = db.Column(db.String(50), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    full_name = db.Column(db.String(120), nullable=False)
    bio = db.Column(db.Text, default="")
    avatar = db.Column(db.String(255), default="")
    cover = db.Column(db.String(255), default="")
    location = db.Column(db.String(120), default="")
    is_admin = db.Column(db.Boolean, default=False, nullable=False)
    is_active_user = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)
    last_seen = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    posts = relationship("Post", back_populates="author", foreign_keys="Post.author_id", cascade="all, delete-orphan")
    comments = relationship("Comment", back_populates="author", cascade="all, delete-orphan")
    reactions = relationship("Reaction", back_populates="user", cascade="all, delete-orphan")
    saves = relationship("Save", back_populates="user", cascade="all, delete-orphan")
    notifications = relationship(
        "Notification", back_populates="user",
        foreign_keys="Notification.user_id", cascade="all, delete-orphan",
    )

    def set_password(self, pw):
        self.password_hash = generate_password_hash(pw)

    def check_password(self, pw):
        return check_password_hash(self.password_hash, pw)

    def avatar_url(self):
        if self.avatar:
            return f"/static/uploads/avatars/{self.avatar}"
        # Deterministic placeholder color based on user id
        return None

    def initials(self):
        parts = (self.full_name or self.username or "?").split()
        return (parts[0][:1] + (parts[-1][:1] if len(parts) > 1 else "")).upper()

    def friends_ids(self):
        """Return list of user ids that are mutually accepted friends."""
        rows = db.session.query(Friendship).filter(
            or_(Friendship.user_id == self.id, Friendship.friend_id == self.id),
            Friendship.status == "accepted",
        ).all()
        ids = set()
        for r in rows:
            ids.add(r.friend_id if r.user_id == self.id else r.user_id)
        return list(ids)

    def friend_request_status_with(self, other_id):
        """Return 'none', 'pending_out', 'pending_in', 'accepted', 'blocked'."""
        if other_id == self.id:
            return "self"
        r = db.session.query(Friendship).filter(
            or_(
                and_(Friendship.user_id == self.id, Friendship.friend_id == other_id),
                and_(Friendship.user_id == other_id, Friendship.friend_id == self.id),
            )
        ).first()
        if not r:
            return "none"
        if r.status == "accepted":
            return "accepted"
        if r.status == "pending":
            return "pending_out" if r.user_id == self.id else "pending_in"
        return r.status

    def follows_page(self, page_id):
        return db.session.query(PageFollow).filter_by(user_id=self.id, page_id=page_id).first() is not None

    def is_member_of_group(self, group_id):
        return db.session.query(GroupMember).filter_by(user_id=self.id, group_id=group_id).first() is not None

    def has_saved(self, post_id):
        return db.session.query(Save).filter_by(user_id=self.id, post_id=post_id).first() is not None

    def __repr__(self):
        return f"<User {self.username}>"


class Friendship(db.Model):
    __tablename__ = "friendships"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    friend_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    status = db.Column(db.String(20), default="pending", nullable=False)  # pending, accepted, blocked
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    accepted_at = db.Column(db.DateTime)

    __table_args__ = (
        UniqueConstraint("user_id", "friend_id", name="uq_friend_pair"),
        Index("ix_friend_user", "user_id"),
        Index("ix_friend_friend", "friend_id"),
        Index("ix_friend_status", "status"),
    )


# ---------- PAGES & GROUPS ----------

class Page(db.Model):
    __tablename__ = "pages"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False, index=True)
    slug = db.Column(db.String(140), unique=True, nullable=False, index=True)
    description = db.Column(db.Text, default="")
    category = db.Column(db.String(60), default="General")
    cover = db.Column(db.String(255), default="")
    avatar = db.Column(db.String(255), default="")
    owner_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    owner = relationship("User", backref="owned_pages")
    followers = relationship("PageFollow", back_populates="page", cascade="all, delete-orphan")

    def avatar_url(self):
        if self.avatar:
            return f"/static/uploads/images/{self.avatar}"
        return None

    def follower_count(self):
        return db.session.query(func.count(PageFollow.id)).filter_by(page_id=self.id).scalar()


class PageFollow(db.Model):
    __tablename__ = "page_follows"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    page_id = db.Column(db.Integer, db.ForeignKey("pages.id", ondelete="CASCADE"), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    page = relationship("Page", back_populates="followers")
    user = relationship("User", backref="page_follows")

    __table_args__ = (UniqueConstraint("user_id", "page_id", name="uq_page_follow"),)


class Group(db.Model):
    __tablename__ = "groups"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False, index=True)
    slug = db.Column(db.String(140), unique=True, nullable=False, index=True)
    description = db.Column(db.Text, default="")
    cover = db.Column(db.String(255), default="")
    privacy = db.Column(db.String(20), default="public")  # public or private
    created_by = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    creator = relationship("User", backref="created_groups")
    members = relationship("GroupMember", back_populates="group", cascade="all, delete-orphan")

    def member_count(self):
        return db.session.query(func.count(GroupMember.id)).filter_by(group_id=self.id).scalar()


class GroupMember(db.Model):
    __tablename__ = "group_members"
    id = db.Column(db.Integer, primary_key=True)
    group_id = db.Column(db.Integer, db.ForeignKey("groups.id", ondelete="CASCADE"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    role = db.Column(db.String(20), default="member")  # member, admin
    joined_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    group = relationship("Group", back_populates="members")
    user = relationship("User", backref="group_memberships")

    __table_args__ = (UniqueConstraint("group_id", "user_id", name="uq_group_member"),)


# ---------- POSTS ----------

class Post(db.Model):
    __tablename__ = "posts"
    id = db.Column(db.Integer, primary_key=True)

    # Authorship: either by user, or on behalf of page/group
    author_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    page_id = db.Column(db.Integer, db.ForeignKey("pages.id", ondelete="SET NULL"), nullable=True, index=True)
    group_id = db.Column(db.Integer, db.ForeignKey("groups.id", ondelete="SET NULL"), nullable=True, index=True)

    content = db.Column(db.Text, default="")
    post_type = db.Column(db.String(30), default="text", nullable=False, index=True)
    # post_type: text, photo, album, video, short_video, link, poll, shared, event, birthday, sponsored

    # Contextual fields
    location = db.Column(db.String(200), default="")
    feeling = db.Column(db.String(60), default="")
    activity = db.Column(db.String(60), default="")

    # Link preview fields
    link_url = db.Column(db.String(500), default="")
    link_title = db.Column(db.String(300), default="")
    link_description = db.Column(db.Text, default="")
    link_image = db.Column(db.String(500), default="")

    # Shared post reference
    shared_post_id = db.Column(db.Integer, db.ForeignKey("posts.id", ondelete="SET NULL"), nullable=True)

    # Event/birthday fields
    event_title = db.Column(db.String(200), default="")
    event_date = db.Column(db.DateTime, nullable=True)

    # Visibility
    visibility = db.Column(db.String(30), default="friends", nullable=False, index=True)
    # public, friends, friends_of_friends, only_me

    # Flags
    is_sponsored = db.Column(db.Boolean, default=False, nullable=False, index=True)
    is_deleted = db.Column(db.Boolean, default=False, nullable=False, index=True)
    is_pinned = db.Column(db.Boolean, default=False, nullable=False)

    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Aggregates (denormalized for feed speed, updated on writes)
    reaction_count = db.Column(db.Integer, default=0, nullable=False)
    comment_count = db.Column(db.Integer, default=0, nullable=False)
    share_count = db.Column(db.Integer, default=0, nullable=False)
    view_count = db.Column(db.Integer, default=0, nullable=False)
    total_watch_seconds = db.Column(db.Integer, default=0, nullable=False)

    # Relationships
    author = relationship("User", back_populates="posts", foreign_keys=[author_id])
    page = relationship("Page", backref="posts")
    group = relationship("Group", backref="posts")
    media = relationship("PostMedia", back_populates="post", cascade="all, delete-orphan", order_by="PostMedia.order_index")
    comments = relationship("Comment", back_populates="post", cascade="all, delete-orphan")
    reactions = relationship("Reaction", back_populates="post", cascade="all, delete-orphan")
    saves = relationship("Save", back_populates="post", cascade="all, delete-orphan")
    poll = relationship("Poll", back_populates="post", uselist=False, cascade="all, delete-orphan")
    tagged_users = relationship("PostTag", back_populates="post", cascade="all, delete-orphan")
    shared_post = relationship("Post", remote_side=[id], foreign_keys=[shared_post_id])

    __table_args__ = (
        Index("ix_post_author_created", "author_id", "created_at"),
        Index("ix_post_page_created", "page_id", "created_at"),
        Index("ix_post_group_created", "group_id", "created_at"),
        Index("ix_post_visibility_created", "visibility", "created_at"),
    )

    def engagement_score(self):
        """Raw engagement number used in ranking."""
        return self.reaction_count + 2 * self.comment_count + 3 * self.share_count

    def reaction_breakdown(self):
        rows = db.session.query(Reaction.reaction_type, func.count(Reaction.id)).filter_by(post_id=self.id).group_by(Reaction.reaction_type).all()
        return {r[0]: r[1] for r in rows}

    def current_user_reaction(self, user_id):
        r = db.session.query(Reaction).filter_by(post_id=self.id, user_id=user_id).first()
        return r.reaction_type if r else None


class PostMedia(db.Model):
    __tablename__ = "post_media"
    id = db.Column(db.Integer, primary_key=True)
    post_id = db.Column(db.Integer, db.ForeignKey("posts.id", ondelete="CASCADE"), nullable=False, index=True)
    media_type = db.Column(db.String(20), nullable=False)  # image, video
    filename = db.Column(db.String(255), nullable=False)
    order_index = db.Column(db.Integer, default=0, nullable=False)
    width = db.Column(db.Integer)
    height = db.Column(db.Integer)

    post = relationship("Post", back_populates="media")

    def url(self):
        sub = "videos" if self.media_type == "video" else "images"
        return f"/static/uploads/{sub}/{self.filename}"


class PostTag(db.Model):
    __tablename__ = "post_tags"
    id = db.Column(db.Integer, primary_key=True)
    post_id = db.Column(db.Integer, db.ForeignKey("posts.id", ondelete="CASCADE"), nullable=False)
    tagged_user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)

    post = relationship("Post", back_populates="tagged_users")
    user = relationship("User")
    __table_args__ = (UniqueConstraint("post_id", "tagged_user_id", name="uq_post_tag"),)


# ---------- POLLS ----------

class Poll(db.Model):
    __tablename__ = "polls"
    id = db.Column(db.Integer, primary_key=True)
    post_id = db.Column(db.Integer, db.ForeignKey("posts.id", ondelete="CASCADE"), unique=True, nullable=False)
    question = db.Column(db.String(500), nullable=False)
    multi_choice = db.Column(db.Boolean, default=False, nullable=False)
    ends_at = db.Column(db.DateTime, nullable=True)

    post = relationship("Post", back_populates="poll")
    options = relationship("PollOption", back_populates="poll", cascade="all, delete-orphan", order_by="PollOption.id")

    def is_closed(self):
        return self.ends_at is not None and self.ends_at < datetime.utcnow()

    def total_votes(self):
        return db.session.query(func.count(PollVote.id)).filter_by(poll_id=self.id).scalar()

    def user_voted_options(self, user_id):
        rows = db.session.query(PollVote.option_id).filter_by(poll_id=self.id, user_id=user_id).all()
        return {r[0] for r in rows}


class PollOption(db.Model):
    __tablename__ = "poll_options"
    id = db.Column(db.Integer, primary_key=True)
    poll_id = db.Column(db.Integer, db.ForeignKey("polls.id", ondelete="CASCADE"), nullable=False, index=True)
    text = db.Column(db.String(200), nullable=False)

    poll = relationship("Poll", back_populates="options")

    def vote_count(self):
        return db.session.query(func.count(PollVote.id)).filter_by(option_id=self.id).scalar()


class PollVote(db.Model):
    __tablename__ = "poll_votes"
    id = db.Column(db.Integer, primary_key=True)
    poll_id = db.Column(db.Integer, db.ForeignKey("polls.id", ondelete="CASCADE"), nullable=False)
    option_id = db.Column(db.Integer, db.ForeignKey("poll_options.id", ondelete="CASCADE"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (UniqueConstraint("poll_id", "option_id", "user_id", name="uq_poll_user_option"),)


# ---------- INTERACTIONS ----------

class Reaction(db.Model):
    __tablename__ = "reactions"
    id = db.Column(db.Integer, primary_key=True)
    post_id = db.Column(db.Integer, db.ForeignKey("posts.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    reaction_type = db.Column(db.String(20), default="like", nullable=False)  # like, love, haha, wow, sad, angry
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    post = relationship("Post", back_populates="reactions")
    user = relationship("User", back_populates="reactions")

    __table_args__ = (UniqueConstraint("post_id", "user_id", name="uq_reaction_unique_user_post"),)


class Comment(db.Model):
    __tablename__ = "comments"
    id = db.Column(db.Integer, primary_key=True)
    post_id = db.Column(db.Integer, db.ForeignKey("posts.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    parent_id = db.Column(db.Integer, db.ForeignKey("comments.id", ondelete="CASCADE"), nullable=True)
    content = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)

    post = relationship("Post", back_populates="comments")
    author = relationship("User", back_populates="comments")
    replies = relationship("Comment", backref=db.backref("parent", remote_side=[id]), cascade="all, delete-orphan")


class Save(db.Model):
    __tablename__ = "saves"
    id = db.Column(db.Integer, primary_key=True)
    post_id = db.Column(db.Integer, db.ForeignKey("posts.id", ondelete="CASCADE"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    post = relationship("Post", back_populates="saves")
    user = relationship("User", back_populates="saves")

    __table_args__ = (UniqueConstraint("post_id", "user_id", name="uq_save_unique"),)


class PostView(db.Model):
    """Records that a user saw a post in their feed, plus dwell/watch time. Used for ranking."""
    __tablename__ = "post_views"
    id = db.Column(db.Integer, primary_key=True)
    post_id = db.Column(db.Integer, db.ForeignKey("posts.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    dwell_ms = db.Column(db.Integer, default=0, nullable=False)
    watch_seconds = db.Column(db.Integer, default=0, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)


# ---------- PERSONALIZATION SIGNALS ----------

class UserAffinity(db.Model):
    """Per-user affinity scores to other users/pages/groups. Updated by ranker.
    target_type: 'user' | 'page' | 'group'
    """
    __tablename__ = "user_affinity"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    target_type = db.Column(db.String(10), nullable=False)
    target_id = db.Column(db.Integer, nullable=False)
    score = db.Column(db.Float, default=0.0, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("user_id", "target_type", "target_id", name="uq_affinity_target"),
        Index("ix_affinity_user_type", "user_id", "target_type"),
    )


class UserFeedWeights(db.Model):
    """Per-user learned weights for the ranking algorithm. Every user has one row."""
    __tablename__ = "user_feed_weights"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False)

    # Base ranker weights, mutated based on user's past behavior
    w_affinity = db.Column(db.Float, default=1.0, nullable=False)
    w_engagement = db.Column(db.Float, default=0.6, nullable=False)
    w_recency = db.Column(db.Float, default=1.2, nullable=False)
    w_type_text = db.Column(db.Float, default=1.0, nullable=False)
    w_type_photo = db.Column(db.Float, default=1.0, nullable=False)
    w_type_video = db.Column(db.Float, default=1.0, nullable=False)
    w_type_link = db.Column(db.Float, default=1.0, nullable=False)
    w_type_poll = db.Column(db.Float, default=1.0, nullable=False)
    w_exploration = db.Column(db.Float, default=0.15, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


# ---------- NOTIFICATIONS ----------

class Notification(db.Model):
    __tablename__ = "notifications"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    actor_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    notif_type = db.Column(db.String(40), nullable=False)  # reacted, commented, friend_request, friend_accept, tagged, shared, mentioned
    post_id = db.Column(db.Integer, db.ForeignKey("posts.id", ondelete="CASCADE"), nullable=True)
    comment_id = db.Column(db.Integer, db.ForeignKey("comments.id", ondelete="SET NULL"), nullable=True)
    content = db.Column(db.String(500), default="")
    is_read = db.Column(db.Boolean, default=False, nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)

    user = relationship("User", back_populates="notifications", foreign_keys=[user_id])
    actor = relationship("User", foreign_keys=[actor_id])
    post = relationship("Post")


class Report(db.Model):
    """Reports filed by users against posts/comments/users, for admin moderation."""
    __tablename__ = "reports"
    id = db.Column(db.Integer, primary_key=True)
    reporter_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    target_type = db.Column(db.String(20), nullable=False)  # post, comment, user
    target_id = db.Column(db.Integer, nullable=False)
    reason = db.Column(db.String(500), default="")
    status = db.Column(db.String(20), default="open")  # open, resolved, dismissed
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    reporter = relationship("User")
