"""Smoke test: exercise every route and check no template errors."""
import sys
from app import create_app
from app.extensions import db
from app.models import User

app = create_app()
app.config["WTF_CSRF_ENABLED"] = False

failures = []
passes = []

def check(label, resp, expected_codes=(200, 302)):
    if resp.status_code in expected_codes:
        passes.append(f"  ✓ [{resp.status_code}] {label}")
    else:
        body = resp.get_data(as_text=True)
        snippet = body[:800].replace("\n", " ")
        failures.append(f"  ✗ [{resp.status_code}] {label}\n      {snippet}")

with app.test_client() as client:
    # Unauthenticated
    check("GET /", client.get("/"))
    check("GET /auth/login", client.get("/auth/login"))
    check("GET /auth/signup", client.get("/auth/signup"))

    # Login
    resp = client.post(
        "/auth/login",
        data={"identifier": "alice", "password": "password123"},
        follow_redirects=False,
    )
    check("POST /auth/login (alice)", resp, expected_codes=(302,))

    # Authenticated pages
    routes = [
        ("GET /feed", "/feed"),
        ("GET /feed/more?page=2", "/feed/more?page=2"),
        ("GET /saved", "/saved"),
        ("GET /search", "/search?q=alice"),
        ("GET /posts/new", "/posts/new"),
        ("GET /u/alice", "/u/alice"),
        ("GET /u/alice/friends", "/u/alice/friends"),
        ("GET /u/friend-requests", "/u/friend-requests"),
        ("GET /u/notifications", "/u/notifications"),
        ("GET /u/settings", "/u/settings"),
        ("GET /groups/", "/groups/"),
        ("GET /groups/new", "/groups/new"),
        ("GET /groups/batch-2024", "/groups/batch-2024"),
        ("GET /pages/", "/pages/"),
        ("GET /pages/new", "/pages/new"),
        ("GET /pages/nielit-updates", "/pages/nielit-updates"),
        ("GET /admin/", "/admin/"),
        ("GET /admin/users", "/admin/users"),
        ("GET /admin/posts", "/admin/posts"),
        ("GET /admin/sponsored/new", "/admin/sponsored/new"),
        ("GET /admin/reports", "/admin/reports"),
    ]
    for label, url in routes:
        check(label, client.get(url))

    # Post detail (post id = 1 from seed)
    check("GET /posts/1", client.get("/posts/1"))
    check("GET /posts/1/insights", client.get("/posts/1/insights"))

    # Mutating endpoints
    from io import BytesIO
    # Create a text post
    check("POST /posts/new (text)", client.post(
        "/posts/new",
        data={"content": "Hello from smoke test!", "visibility": "friends", "target_kind": "profile"},
        content_type='multipart/form-data',
    ))
    # Create poll post
    check("POST /posts/new (poll)", client.post(
        "/posts/new",
        data={
            "content": "Pick one:", "visibility": "public", "target_kind": "profile",
            "poll_question": "Best language?", "poll_options": ["Python", "JS", "Rust"],
        },
        content_type='multipart/form-data',
    ))

    # Create group
    check("POST /groups/new", client.post("/groups/new", data={"name": "Test Group", "description": "Test", "privacy": "public"}, content_type='multipart/form-data'))
    # Create page
    check("POST /pages/new", client.post("/pages/new", data={"name": "Test Page", "description": "Test", "category": "Education"}, content_type='multipart/form-data'))

    # API: react
    check("POST /api/react", client.post("/api/react", data={"post_id": "1", "reaction_type": "love"}))
    # API: save
    check("POST /api/save", client.post("/api/save", data={"post_id": "1"}))
    # API: comment
    check("POST /api/comment", client.post("/api/comment", data={"post_id": "1", "content": "Smoke test comment"}))
    # API: view-metrics
    check("POST /api/view-metrics", client.post("/api/view-metrics", data={"post_id": "1", "dwell_ms": "2500", "watch_seconds": "3"}))
    # API: notifications
    check("GET /api/notifications", client.get("/api/notifications"))

    # Friend request flow
    check("POST /u/friend-request", client.post("/u/friend-request", data={"user_id": "3"}))

    # Share a post
    check("POST /posts/1/share", client.post("/posts/1/share", data={"content": "Check this out", "visibility": "friends"}))

    # Vote on the poll we created
    from app.models import Poll, PollOption
    with app.app_context():
        poll = Poll.query.first()
        opt = PollOption.query.filter_by(poll_id=poll.id).first() if poll else None
    if opt:
        check("POST /posts/poll/N/vote", client.post(f"/posts/poll/{poll.id}/vote", data={"option_id": str(opt.id)}))

    # Logout
    check("POST /auth/logout", client.post("/auth/logout"))
    # Anonymous redirects
    check("GET /feed (anon)", client.get("/feed"), expected_codes=(302,))

print("\n".join(passes))
if failures:
    print("\n==== FAILURES ====")
    print("\n".join(failures))
    sys.exit(1)
print(f"\nAll {len(passes)} routes passed ✓")
