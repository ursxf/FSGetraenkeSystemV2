from hashlib import sha256
from typing import Optional

from flask import current_app, session
from flask_login import current_user

from .db.models import Revenue


def format_currency(value: int, factor: int = 100) -> str:
    return f'{value / factor:.2f} €'.replace('.', ',')


def check_hash(hash_to_check: str, value: str) -> bool:
    hashed_value = sha256(value.encode('utf-8')).hexdigest()

    if hash_to_check == hashed_value:
        return True

    return False


def calc_hash(value: str) -> str:
    return sha256(value.encode('utf-8')).hexdigest()


def get_user_id() -> Optional[int]:
    impersonate_user_id = session.get('impersonate', None)
    return impersonate_user_id if impersonate_user_id is not None else current_user.id


def revenue_is_cancelable(revenue: Revenue | None) -> bool:
    if revenue is None:
        return False

    if revenue.age.total_seconds() < current_app.config.get('QUICK_CANCEL_SEC'):
        return True

    return False
