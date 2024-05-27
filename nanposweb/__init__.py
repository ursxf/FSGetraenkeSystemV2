import contextlib
from importlib import metadata
from pathlib import Path

from flask import Flask, flash, redirect, session, url_for
from flask_login import LoginManager, current_user
from flask_principal import Principal, RoleNeed, UserNeed, identity_loaded
from werkzeug.wrappers import Response

from .account import account_bp
from .admin import admin_bp
from .auth import auth_bp
from .db import db
from .db.helpers import get_balance
from .db.models import User
from .helpers import format_currency, get_user_id
from .main import main_bp


def create_app(test_config: dict | None = None) -> Flask:  # noqa: C901
    # create and configure the nanposweb_app
    nanposweb_app = Flask(__name__, instance_relative_config=True)
    nanposweb_app.config.from_mapping(
        SESSION_COOKIE_SAMESITE='Strict',
        SESSION_COOKIE_SECURE=True,
        REMEMBER_COOKIE_SECURE=True,
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        SQLALCHEMY_DATABASE_URI='postgresql://nanpos:nanpos@localhost:5432/nanpos',
        TERMINAL_LOGOUT_TIMEOUT=30,  # logout timeout for Terminal mode in seconds, set to none to disable
        QUICK_CANCEL_SEC=60,  # Second-Limit for canceling a revenue
        BANK_DATA=None,
        FAVORITES_DISPLAY=3,  # Amount of favorite products which should get highlighted
        FAVORITES_DAYS=100,  # Timespan for calculation of favorite products in Days
    )
    if nanposweb_app.debug:
        nanposweb_app.config.from_mapping(
            SECRET_KEY='debug',  # noqa: S106 nosec
            TESTING=True,
            SESSION_COOKIE_SAMESITE=None,
            SESSION_COOKIE_SECURE=False,
            REMEMBER_COOKIE_SECURE=False,
        )

    if test_config is None:
        # load the instance config, if it exists, when not testing
        nanposweb_app.config.from_pyfile('config.py', silent=True)
    else:
        # load the test config if passed in
        nanposweb_app.config.from_mapping(test_config)

    # ensure the instance folder exists
    with contextlib.suppress(OSError):
        Path(nanposweb_app.instance_path).mkdir(parents=True)

    db.init_app(nanposweb_app)

    Principal(nanposweb_app)

    login_manager = LoginManager()
    login_manager.login_message_category = 'info'
    login_manager.init_app(nanposweb_app)

    @login_manager.unauthorized_handler
    def unauthorized() -> Response:
        if login_manager.localize_callback is not None:
            flash(login_manager.localize_callback(login_manager.login_message),
                  category=login_manager.login_message_category)
        else:
            flash(login_manager.login_message, category=login_manager.login_message_category)

        if session.get('terminal', False):
            return redirect(url_for('auth.login', terminal=True))

        return redirect(url_for('auth.login'))

    @login_manager.user_loader
    def load_user(user_id: int) -> User:
        return User.query.get(user_id)

    @identity_loaded.connect_via(nanposweb_app)
    def on_identity_loaded(sender, identity):  # noqa: ANN001
        # Set the identity user object
        identity.user = current_user

        # Add the UserNeed to the identity
        if hasattr(current_user, 'id'):
            identity.provides.add(UserNeed(current_user.id))

        # Add the 'admin' RoleNeed to the identity
        if hasattr(current_user, 'isop'):
            identity.provides.add(RoleNeed('admin'))

    nanposweb_app.jinja_env.filters.update(
        format_currency=format_currency,
    )

    @nanposweb_app.context_processor
    def functions() -> dict:
        return {'get_balance': get_balance, 'get_user_id': get_user_id}

    @nanposweb_app.context_processor
    def get_version() -> dict:
        version = 'devel' if nanposweb_app.debug else metadata.version('nanposweb')
        return {'version': version}

    @nanposweb_app.context_processor
    def get_utils() -> dict:
        utils = []
        if nanposweb_app.config.get('BANK_DATA', False):
            utils.append(('main.bank_account', 'Bank Account'))
        if nanposweb_app.config.get('utils', False):
            utils.extend(nanposweb_app.config['utils'])
        return {'utils': utils}

    # blueprint for auth routes in our nanposweb_app
    nanposweb_app.register_blueprint(auth_bp)

    # blueprint for main parts of nanposweb_app
    nanposweb_app.register_blueprint(main_bp)

    # blueprint for account management
    nanposweb_app.register_blueprint(account_bp)

    # blueprint for admin parts of nanposweb_app
    nanposweb_app.register_blueprint(admin_bp)

    return nanposweb_app


app = create_app()
