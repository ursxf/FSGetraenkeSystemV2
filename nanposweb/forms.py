from flask_wtf import FlaskForm
from wtforms import BooleanField, IntegerField, PasswordField, StringField, SubmitField
from wtforms.validators import InputRequired, Length, Optional


class LoginForm(FlaskForm):
    username = StringField(
        label='Username',
        validators=[InputRequired()],
        render_kw={'placeholder': 'Username', 'autofocus': True},
    )
    pin = PasswordField(
        label='PIN',
        validators=[InputRequired()],
        render_kw={'placeholder': 'PIN'},
    )
    remember = BooleanField(
        label='Remember me',
    )
    submit = SubmitField(
        label='Sign in',
    )


class MainForm(FlaskForm):
    ean = IntegerField(
        label='EAN',
        validators=[Optional()],
        render_kw={'placeholder': 'EAN', 'autofocus': True},
    )


class PinForm(FlaskForm):
    old_pin = PasswordField(
        label='Old PIN',
        validators=[InputRequired()],
        render_kw={'placeholder': 'pin'},
    )
    unset_pin = BooleanField(
        label='Unset PIN',
    )
    new_pin = PasswordField(
        label='New PIN',
        render_kw={'placeholder': 'pin'},
    )
    confirm_pin = PasswordField(
        label='Confirm new PIN',
        render_kw={'placeholder': 'pin'},
    )
    change_pin = SubmitField(
        label='Change PIN',
    )


class CardForm(FlaskForm):
    card_name = StringField(
        label='Name',
        validators=[Length(max=100)],
        render_kw={'placeholder': 'e.g. Key tag'},
    )
    card_number = StringField(
        label='Card ID',
        validators=[InputRequired()],
        render_kw={'placeholder': 'Card ID'},
    )
    add_card = SubmitField(
        label='Add Card',
    )


class CardRenameForm(FlaskForm):
    name = StringField(
        label='Name',
        validators=[InputRequired(), Length(max=100)],
    )
