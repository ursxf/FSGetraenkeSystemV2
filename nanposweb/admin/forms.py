from flask_wtf import FlaskForm
from wtforms import BooleanField, DecimalField, IntegerField, PasswordField, StringField, SubmitField
from wtforms.validators import InputRequired, Length, Optional


class ProductForm(FlaskForm):
    id = IntegerField(
        label='ID',
        render_kw={'placeholder': 'id', 'readonly': ''},
    )
    name = StringField(
        label='Name',
        validators=[InputRequired()],
        render_kw={'placeholder': 'name'},
    )
    ean = IntegerField(
        label='EAN',
        validators=[Optional(strip_whitespace=True)],
        render_kw={'placeholder': 'ean'},
    )
    price = IntegerField(
        label='Price',
        validators=[InputRequired()],
        render_kw={'placeholder': 'price'},
    )
    visible = BooleanField(
        label='Visible',
    )
    has_alc = BooleanField(
        label='Has Alcohol',
    )
    is_food = BooleanField(
        label='Is Food',
    )


class UserForm(FlaskForm):
    id = IntegerField(
        label='ID',
        render_kw={'placeholder': 'id', 'readonly': ''},
    )
    name = StringField(
        label='Name',
        validators=[InputRequired()],
        render_kw={'placeholder': 'name'},
    )
    card = StringField(
        label='Add Card ID',
        render_kw={'placeholder': 'Card ID'},
    )
    card_name = StringField(
        label='Card name',
        validators=[Length(max=100)],
        render_kw={'placeholder': 'Card name'},
    )
    pin = PasswordField(
        label='PIN',
        render_kw={'placeholder': 'pin'},
    )
    unset_pin = BooleanField(
        label='Unset PIN',
    )
    isop = BooleanField(
        label='Admin',
    )


class BalanceForm(FlaskForm):
    amount = DecimalField(
        label='Amount',
        validators=[InputRequired()],
        render_kw={'placeholder': '0.00'},
    )
    recharge = SubmitField(label='Recharge')
    charge = SubmitField(label='Charge')
