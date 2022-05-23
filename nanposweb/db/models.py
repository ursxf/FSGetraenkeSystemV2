from datetime import datetime, timezone
from flask_login import UserMixin
import sqlalchemy as sa

from . import db


class User(db.Model, UserMixin):
    __tablename__ = 'users'
    id = db.Column('id', db.Integer, primary_key=True)
    name = db.Column('name', db.VARCHAR(200), nullable=False, unique=True)
    card = db.Column('card', db.VARCHAR(500))
    isop = db.Column('isop', db.Boolean, server_default=db.false(), nullable=False)
    pin = db.Column('pin', db.VARCHAR(500))


class Product(db.Model):
    __tablename__ = 'products'
    id = db.Column('id', db.Integer, primary_key=True)
    name = db.Column('name', db.VARCHAR(50), nullable=False, unique=True)
    ean = db.Column('ean', db.BigInteger, unique=True)
    price = db.Column('price', db.Integer, nullable=False)
    visible = db.Column('visible', db.Boolean, nullable=False, server_default=db.true())
    has_alc = db.Column('has_alc', db.Boolean, nullable=False, server_default=db.false())
    is_food = db.Column('is_food', db.Boolean, nullable=False, server_default=db.false())

# See https://mike.depalatis.net/blog/sqlalchemy-timestamps.html
class TimeStamp(sa.types.TypeDecorator):
    impl = sa.types.DateTime
    cache_ok = False
    LOCAL_TIMEZONE = datetime.utcnow().astimezone().tzinfo

    def process_bind_param(self, value: datetime, dialect):
        if value.tzinfo is None:
            value = value.astimezone(self.LOCAL_TIMEZONE)

        return value.astimezone(timezone.utc)

    def process_result_value(self, value, dialect):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)

        return value.astimezone(timezone.utc)

class Revenue(db.Model):
    __tablename__ = 'revenues'
    id = db.Column('id', db.Integer, primary_key=True)
    user = db.Column('user', db.Integer, db.ForeignKey('users.id'), nullable=False)
    product = db.Column('product', db.Integer, db.ForeignKey('products.id'))
    amount = db.Column('amount', db.Integer, nullable=False)
    date = db.Column('date', TimeStamp(), server_default=db.func.now())

    @property
    def age(self):
        age = datetime.now(self.date.tzinfo) - self.date
        return age
