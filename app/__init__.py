import logging
import os
from flask import Flask, jsonify, request
from werkzeug.middleware.proxy_fix import ProxyFix

from app.config import Config, LANGS
from app import db, natlas_client, pipeline, course_memory


def create_app(overrides: dict | None = None) -> Flask:
    flask_app = Flask(__name__, template_folder="../templates", static_folder="../static")
    flask_app.config.from_object(Config)
    flask_app.wsgi_app = ProxyFix(flask_app.wsgi_app, x_for=1, x_proto=1, x_host=1)  # trust the host's proxy headers
    if overrides:
        flask_app.config.update(overrides)
    logging.basicConfig(level=logging.INFO)

    os.makedirs(os.path.dirname(os.path.abspath(flask_app.config["DB_PATH"])), exist_ok=True)
    db.init(flask_app.config["DB_PATH"])
    course_memory.init(flask_app.config["DB_PATH"])
    registered = db.get_setting("gateway_url")   # set by the GPU notebook heartbeat (see /internal/gateway)
    natlas_client.configure(registered or flask_app.config["GATEWAY_URL"], flask_app.config["GATEWAY_KEY"])
    pipeline.SETTINGS["max_audio_s"] = flask_app.config["MAX_AUDIO_S"]
    pipeline.SETTINGS["max_summary_audio_s"] = flask_app.config["MAX_SUMMARY_AUDIO_S"]
    flask_app.config["LANG_OPTIONS"] = {c: LANGS[c] for c in LANGS if c in flask_app.config["ENABLED_LANGS"]}

    from app.routes import bp
    flask_app.register_blueprint(bp)

    def _json_error(status, message):
        if request.path.startswith("/api/"):
            return jsonify(ok=False, message=message), status
        return message, status

    @flask_app.errorhandler(413)
    def too_large(_e):
        return _json_error(413, "That recording is too large. Please record a shorter question.")

    @flask_app.errorhandler(500)
    def server_error(_e):
        return _json_error(500, "Something went wrong on the server. Please try again.")

    flask_app.logger.info("WhatsApp channel: %s", "ENABLED" if flask_app.config["WHATSAPP_ENABLED"] else "disabled")
    if flask_app.config["WHATSAPP_ENABLED"]:  # optional channel; web works without it
        from app.whatsapp import bp as wa_bp
        flask_app.register_blueprint(wa_bp)
    return flask_app
