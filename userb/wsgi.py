"""WSGI entrypoint. Gunicorn loads this."""
from app import create_app

application = create_app()
app = application  # Flask CLI convention

if __name__ == "__main__":
    application.run(host="0.0.0.0", port=5000, debug=False)
