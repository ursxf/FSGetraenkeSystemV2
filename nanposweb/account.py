from flask import Blueprint, Response, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from wtforms.validators import InputRequired

from .db import db
from .db.helpers import get_balance, revenue_query
from .forms import CardForm, PinForm
from .helpers import calc_hash, check_hash

account_bp = Blueprint('account', __name__, url_prefix='/account')


@account_bp.route('/revenues')
@login_required
def revenues() -> str:
    balance = get_balance(current_user.id)
    revenues_query = revenue_query(current_user.id)
    revenues_result = db.session.execute(revenues_query).all()
    return render_template('account/index.html', balance=balance, revenues=revenues_result)


@account_bp.route('/pin', methods=['GET', 'POST'])
@login_required
def pin() -> Response | str:
    form = PinForm()

    no_pin_attrs = ['readonly', 'disabled']
    if current_user.pin is None:
        for item in no_pin_attrs:
            form.old_pin.render_kw[item] = ''
        form.old_pin.validators = []
    else:
        for item in no_pin_attrs:
            form.old_pin.render_kw.pop(item, None)
        form.old_pin.validators = [InputRequired()]

    if request.method == 'POST':
        if form.validate_on_submit():
            if current_user.pin is not None and not check_hash(current_user.pin, form.old_pin.data):
                flash('Old PIN is not correct', category='danger')
                return render_template('account/change_pin.html', form=form)

            if form.new_pin.data != form.confirm_pin.data:
                flash('New PIN and Confirmation do not match', category='danger')
                return render_template('account/change_pin.html', form=form)

            if form.unset_pin.data:
                current_user.pin = None
                flash('Unset PIN', category='success')
            else:
                current_user.pin = calc_hash(form.new_pin.data)
                flash('Changed PIN', category='success')

            db.session.commit()
            return redirect(url_for('main.index'))

        flash('Submitted form was not valid!', category='danger')

    return render_template('account/change_pin.html', form=form)


@account_bp.route('/card', methods=['GET', 'POST'])
@login_required
def card() -> Response | str:
    form = CardForm()

    if request.method == 'POST':
        if form.validate_on_submit():
            if form.unset_card.data:
                current_user.card = None
                flash('Unset Card', category='success')
            else:
                current_user.card = calc_hash(form.card_number.data)
                flash('Changed Card', category='success')

            db.session.commit()
            return redirect(url_for('main.index'))

        flash('Submitted form was not valid!', category='danger')

    return render_template('account/change_card.html', form=form)
