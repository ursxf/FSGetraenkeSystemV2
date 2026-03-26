import sqlalchemy.sql.selectable
from sqlalchemy.orm import aliased

from . import db
from .models import Product, Revenue, User


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
