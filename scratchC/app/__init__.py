"""Application factory."""
import os
from pathlib import Path
from flask import Flask, redirect, url_for, render_template
from flask_login import current_user

from .extensions import db, migrate, login_manager, csrf
from .config import Config


def create_app(config_class=Config):
    app = Flask(
        __name__,
        template_folder="templates",
        static_folder="static",
    )
    app.config.from_object(config_class)

    # Ensure upload directories exist
    for sub in ("images", "videos", "avatars", "covers"):
        Path(app.config["UPLOAD_FOLDER"], sub).mkdir(parents=True, exist_ok=True)

    # Init extensions
    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    login_manager.login_view = "auth.login"
    login_manager.login_message = "Please sign in to continue."
    login_manager.login_message_category = "info"
    csrf.init_app(app)

    # User loader
    from .models import User

    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(User, int(user_id))

    # Register blueprints
    from .auth.routes import bp as auth_bp
    from .feed.routes import bp as feed_bp
    from .posts.routes import bp as posts_bp
    from .users.routes import bp as users_bp
    from .groups.routes import bp as groups_bp
    from .pages.routes import bp as pages_bp
    from .admin.routes import bp as admin_bp
    from .api.routes import bp as api_bp

    app.register_blueprint(auth_bp, url_prefix="/auth")
    app.register_blueprint(feed_bp)
    app.register_blueprint(posts_bp, url_prefix="/posts")
    app.register_blueprint(users_bp, url_prefix="/u")
    app.register_blueprint(groups_bp, url_prefix="/groups")
    app.register_blueprint(pages_bp, url_prefix="/pages")
    app.register_blueprint(admin_bp, url_prefix="/admin")
    app.register_blueprint(api_bp, url_prefix="/api")

    # Root
    @app.route("/")
    def index():
        if current_user.is_authenticated:
            return redirect(url_for("feed.home"))
        return redirect(url_for("auth.login"))

    # Template globals
    @app.context_processor
    def inject_globals():
        def _get_user(uid):
            if uid is None:
                return None
            return db.session.get(User, int(uid))
        return {
            "APP_NAME": app.config["APP_NAME"],
            "get_user": _get_user,
        }

    # Error handlers
    @app.errorhandler(404)
    def not_found(e):
        return render_template("errors/404.html"), 404

    @app.errorhandler(413)
    def too_large(e):
        return render_template("errors/413.html", max_mb=app.config["MAX_CONTENT_LENGTH"] // (1024 * 1024)), 413

    @app.errorhandler(500)
    def server_error(e):
        return render_template("errors/500.html"), 500

    # Jinja filters
    from .utils.filters import register_filters
    register_filters(app)

    # CLI commands
    @app.cli.command("init-db")
    def init_db_cmd():
        """Create all database tables (first-time setup)."""
        with app.app_context():
            db.create_all()
            print("✓ Tables created.")

    @app.cli.command("promote-admin")
    def promote_admin_cmd():
        """Promote a user to admin by username or email (prompts interactively)."""
        import sys
        ident = input("Username or email to promote: ").strip()
        with app.app_context():
            u = db.session.query(User).filter(
                (User.username == ident) | (User.email == ident)
            ).first()
            if not u:
                print("✗ User not found.", file=sys.stderr)
                return
            u.is_admin = True
            db.session.commit()
            print(f"✓ {u.username} is now an admin.")

    return app
