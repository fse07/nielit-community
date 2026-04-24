"""Authentication routes."""
import re
from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app
from flask_login import login_user, logout_user, login_required, current_user
from email_validator import validate_email, EmailNotValidError

from ..extensions import db
from ..models import User, UserFeedWeights

bp = Blueprint("auth", __name__)


USERNAME_RE = re.compile(r"^[a-z0-9_]{3,30}$")


@bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("feed.home"))

    if request.method == "POST":
        identifier = (request.form.get("identifier") or "").strip().lower()
        password = request.form.get("password") or ""
        remember = bool(request.form.get("remember"))

        if not identifier or not password:
            flash("Please enter email/username and password.", "danger")
            return render_template("auth/login.html")

        user = db.session.query(User).filter(
            (User.email == identifier) | (User.username == identifier)
        ).first()
        if user and user.check_password(password):
            if not user.is_active_user:
                flash("Account is disabled. Contact admin.", "danger")
                return render_template("auth/login.html")
            login_user(user, remember=remember)
            from datetime import datetime
            user.last_seen = datetime.utcnow()
            db.session.commit()
            nxt = request.args.get("next") or url_for("feed.home")
            return redirect(nxt)
        flash("Invalid credentials.", "danger")

    return render_template("auth/login.html")


@bp.route("/signup", methods=["GET", "POST"])
def signup():
    if current_user.is_authenticated:
        return redirect(url_for("feed.home"))

    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        username = (request.form.get("username") or "").strip().lower()
        full_name = (request.form.get("full_name") or "").strip()
        password = request.form.get("password") or ""
        confirm = request.form.get("confirm") or ""

        errors = []
        try:
            validate_email(email, check_deliverability=False)
        except EmailNotValidError:
            errors.append("Invalid email address.")
        if not USERNAME_RE.match(username):
            errors.append("Username must be 3-30 chars, lowercase letters/numbers/underscores only.")
        if not full_name or len(full_name) < 2:
            errors.append("Full name required.")
        if len(password) < 8:
            errors.append("Password must be at least 8 characters.")
        if password != confirm:
            errors.append("Passwords do not match.")

        if not errors:
            if db.session.query(User).filter((User.email == email) | (User.username == username)).first():
                errors.append("Email or username already taken.")

        if errors:
            for e in errors:
                flash(e, "danger")
            return render_template("auth/signup.html",
                                   email=email, username=username, full_name=full_name)

        # First registered user becomes admin
        is_first = db.session.query(User).count() == 0

        user = User(
            email=email, username=username, full_name=full_name,
            is_admin=is_first,
        )
        user.set_password(password)
        db.session.add(user)
        db.session.flush()
        weights = UserFeedWeights(user_id=user.id)
        db.session.add(weights)
        db.session.commit()

        login_user(user)
        flash(f"Welcome to {current_app.config['APP_NAME']}, {user.full_name}!", "success")
        return redirect(url_for("feed.home"))

    return render_template("auth/signup.html")


@bp.route("/logout", methods=["POST"])
@login_required
def logout():
    logout_user()
    flash("You have been signed out.", "info")
    return redirect(url_for("auth.login"))
