import sqlalchemy.sql.selectable

from . import db
from .models import Product, Revenue


def get_balance(user_id: int) -> int:
    stmt = db.select(db.func.coalesce(db.func.sum(Revenue.amount), 0)).where(Revenue.user == user_id)
    return db.session.execute(stmt).scalars().first()


def revenue_query(user_id: int) -> sqlalchemy.sql.selectable.Select:
    return (
        db.select(Revenue, db.func.coalesce(Product.name, ''))
        .outerjoin(Product, Revenue.product == Product.id)
        .where(Revenue.user == user_id)
        .order_by(db.desc(Revenue.date))
    )
