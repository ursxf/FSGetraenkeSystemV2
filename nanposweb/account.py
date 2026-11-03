from typing import Union

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from flask_wtf import FlaskForm
from sqlalchemy.exc import IntegrityError
from werkzeug.wrappers import Response
from wtforms.validators import InputRequired

from .admin.stats import Semester, build_wrapped, local_today, wrapped_semesters, wrapped_window
from .db import db
from .db.helpers import add_card, revenue_query
from .db.models import Card, User
from .forms import CardForm, CardRenameForm, PinForm
from .helpers import calc_hash, check_hash

account_bp = Blueprint('account', __name__, url_prefix='/account')


@account_bp.route('/revenues')
@login_required
def revenues() -> str:
    revenues_query = revenue_query(current_user.id)
    revenues_result = db.session.execute(revenues_query).all()
    return render_template('account/index.html', revenues=revenues_result)


@account_bp.route('/wrapped')
@login_required
def wrapped() -> str:
    """Personal semester in review. Admins can open it for other users with ?user=<id>.

    Users only see the Wrapped of the previous semester during the first months of a semester,
    admins can see every finished semester at any time.
    """
    user_id = current_user.id
    requested = request.args.get('user', type=int)
    if requested is not None and requested != current_user.id:
        if not current_user.isop:
            abort(401)
        if User.query.get(requested) is None:
            abort(404)
        user_id = requested

    open_semester, window_date = wrapped_window(local_today())
    semesters = wrapped_semesters(user_id)
    if not current_user.isop:
        semesters = [s for s in semesters if s == open_semester]
    semester = Semester.parse(request.args.get('semester'))
    if semester not in semesters:
        semester = semesters[0] if semesters else None

    return render_template(
        'account/wrapped.html',
        wrapped=build_wrapped(user_id, semester) if semester is not None else None,
        semesters=semesters,
        semester=semester,
        open_semester=open_semester,
        window_date=window_date,
        user_id=user_id,
        own=user_id == current_user.id,
    )


@account_bp.route('/pin', methods=['GET', 'POST'])
@login_required
def pin() -> Union[Response, str]:
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
            if current_user.pin is not None and not check_hash(current_user.pin, form.old_pin.data or ''):
                flash('Old PIN is not correct', category='danger')
                return render_template('account/change_pin.html', form=form)

            if form.new_pin.data != form.confirm_pin.data:
                flash('New PIN and Confirmation do not match', category='danger')
                return render_template('account/change_pin.html', form=form)

            if form.unset_pin.data:
                current_user.pin = None
                flash('Unset PIN', category='success')
            else:
                if not form.new_pin.data:
                    flash('New PIN has no value', category='danger')
                    return render_template('account/change_pin.html', form=form)
                current_user.pin = calc_hash(form.new_pin.data)
                flash('Changed PIN', category='success')

            db.session.commit()
            return redirect(url_for('main.index'))

        flash('Submitted form was not valid!', category='danger')

    return render_template('account/change_pin.html', form=form)


def _own_card(card_id: int) -> Card:
    card = Card.query.get(card_id)
    if card is None or card.user != current_user.id:
        abort(404)
    return card


@account_bp.route('/card', methods=['GET', 'POST'])
@login_required
def card() -> Union[Response, str]:
    form = CardForm()

    if request.method == 'POST':
        if form.validate_on_submit():
            new_card, error = add_card(current_user, form.card_number.data or '', form.card_name.data)
            if error is None:
                try:
                    db.session.commit()
                except IntegrityError:
                    db.session.rollback()
                    error = 'This card is already registered to another user'
            if error is not None:
                flash(error, category='danger')
                return render_template('account/cards.html', form=form, rename_form=CardRenameForm())

            flash(f'Added card "{new_card.name}"', category='success')
            return redirect(url_for('account.card'))

        flash('Submitted form was not valid!', category='danger')

    return render_template('account/cards.html', form=form, rename_form=CardRenameForm())


@account_bp.route('/card/<int:card_id>/rename', methods=['POST'])
@login_required
def rename_card(card_id: int) -> Response:
    card = _own_card(card_id)
    form = CardRenameForm()
    if form.validate_on_submit() and form.name.data.strip():
        card.name = form.name.data.strip()
        db.session.commit()
        flash(f'Renamed card to "{card.name}"', category='success')
    else:
        flash('Submitted form was not valid!', category='danger')
    return redirect(url_for('account.card'))


@account_bp.route('/card/<int:card_id>/delete', methods=['POST'])
@login_required
def delete_card(card_id: int) -> Response:
    card = _own_card(card_id)
    if FlaskForm().validate_on_submit():
        db.session.delete(card)
        db.session.commit()
        flash(f'Removed card "{card.name}"', category='success')
    else:
        flash('Submitted form was not valid!', category='danger')
    return redirect(url_for('account.card'))
