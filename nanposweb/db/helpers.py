from typing import Optional

import sqlalchemy.sql.selectable
from sqlalchemy.orm import aliased

from . import db
from ..helpers import calc_hash
from .models import Card, Product, Revenue, User


def get_balance(user_id: int) -> int:
    stmt = db.select(db.func.coalesce(db.func.sum(Revenue.amount), 0)).where(Revenue.user == user_id)
    return db.session.execute(stmt).scalars().first()


def revenue_query(user_id: int) -> sqlalchemy.sql.selectable.Select:
    admin_alias = aliased(User)
    return (
        db.select(Revenue, db.func.coalesce(Product.name, ''), db.func.coalesce(admin_alias.name, ''))
        .outerjoin(Product, Revenue.product == Product.id)
        .outerjoin(admin_alias, Revenue.admin_id == admin_alias.id)
        .where(Revenue.user == user_id)
        .order_by(db.desc(Revenue.date))
    )


CARD_NAME_LENGTH = 100


def get_user_by_card(card_uid: str) -> Optional[User]:
    """Return the owner of the card with *card_uid* (plain UID, not hashed)."""
    card = Card.query.filter_by(card=calc_hash(card_uid)).one_or_none()
    return card.owner if card is not None else None


def add_card(user: User, card_uid: str, name: Optional[str]) -> tuple[Optional[Card], Optional[str]]:
    """Register a new card for *user*. Returns the card or an error message, nothing is committed."""
    card_uid = card_uid.strip()
    if not card_uid:
        return None, 'Card ID has no value'
    card_hash = calc_hash(card_uid)
    with db.session.no_autoflush:
        existing = Card.query.filter_by(card=card_hash).one_or_none()
    if existing is not None:
        if existing.user == user.id:
            return None, f'This card is already registered as "{existing.name}"'
        return None, 'This card is already registered to another user'
    name = (name or '').strip()[:CARD_NAME_LENGTH] or f'Card {len(user.cards) + 1}'
    card = Card(card=card_hash, name=name)
    user.cards.append(card)
    return card, None


def migrate_legacy_cards() -> int:
    """Move cards from the old ``users.card`` column into the ``cards`` table. Safe to run repeatedly."""
    db.create_all()
    moved = 0
    for user in User.query.filter(User.card.isnot(None)).all():
        if Card.query.filter_by(card=user.card).one_or_none() is None:
            user.cards.append(Card(card=user.card, name='Card'))
            moved += 1
        user.card = None
    db.session.commit()
    return moved
