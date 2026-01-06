from flask import Flask

from routes.trip_routes import trip_bp


def create_app() -> Flask:
    app = Flask(__name__)
    app.config.from_object("config.Config")

    app.register_blueprint(trip_bp)

    return app


if __name__ == "__main__":
    app = create_app()
    app.run(debug=True)
