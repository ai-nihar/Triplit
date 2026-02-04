from __future__ import annotations

from flask import Flask


def create_app(config_name: str | None = None) -> Flask:
    """Application factory."""
    # Load environment variables from .env if python-dotenv is installed.
    try:
        from dotenv import load_dotenv

        load_dotenv()
    except Exception:
        pass

    app = Flask(__name__, template_folder="templates", static_folder="static")

    from config import get_config

    app.config.from_object(get_config(config_name))

    from routes.web import web_bp

    app.register_blueprint(web_bp)

    @app.get("/health")
    def health():
        return {"status": "ok"}, 200

    return app


app = create_app()


if __name__ == "__main__":
    app.run()
