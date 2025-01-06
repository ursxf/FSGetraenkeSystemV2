from hashlib import sha256
from typing import Optional

from flask import current_app, session
from flask_login import current_user

from .db.models import Revenue


def format_currency(value: int, factor: int = 100) -> str:
    return f'{value / factor:.2f} €'.replace('.', ',')


def check_hash(hash_to_check: str, value: str) -> bool:
    hashed_value = sha256(value.encode('utf-8')).hexdigest()

    return hash_to_check == hashed_value


def calc_hash(value: str) -> str:
    return sha256(value.encode('utf-8')).hexdigest()


def get_user_id() -> int:
    impersonate_user_id = session.get('impersonate', None)
    return impersonate_user_id if impersonate_user_id is not None else current_user.id


def revenue_is_cancelable(revenue: Optional[Revenue]) -> bool:
    if revenue is None:
        return False

    return revenue.age.total_seconds() < current_app.config.get('QUICK_CANCEL_SEC', 0)
