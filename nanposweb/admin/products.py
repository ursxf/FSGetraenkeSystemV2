from flask import Blueprint, flash, redirect, render_template, url_for
from flask_login import login_required
from werkzeug.wrappers import Response

from .forms import ProductForm
from .helpers import admin_permission
from ..db import db
from ..db.models import Product

products_bp = Blueprint('products', __name__, url_prefix='/products')


@products_bp.route('/')
@login_required
@admin_permission.require(http_exception=401)
def index() -> str:
    products = Product.query.order_by(Product.name).all()
    return render_template('products/index.html', products=products)


@products_bp.route('/', methods=['POST'])
@login_required
@admin_permission.require(http_exception=401)
def post() -> Response | str:
    form = ProductForm()
    if not form.validate_on_submit():
        flash('Submitted form was not valid!', category='danger')
        return render_template('products/form.html', form=form, edit=True)

    item = Product.query.filter_by(id=form.id.data).one_or_none()
    if item is None:
        new = Product(
            name=form.name.data,
            ean=form.ean.data,
            price=form.price.data,
            visible=form.visible.data,
            has_alc=form.has_alc.data,
            is_food=form.is_food.data
        )
        db.session.add(new)
        db.session.commit()
        flash(f'Created products "{form.name.data}"', category='success')
    else:
        item.name = form.name.data
        item.ean = form.ean.data
        item.price = form.price.data
        item.visible = form.visible.data
        item.has_alc = form.has_alc.data
        item.is_food = form.is_food.data
        db.session.commit()
        flash(f'Updated products "{form.name.data}"', category='success')

    return redirect(url_for('admin.products.index'))


@products_bp.route('/add')
@login_required
@admin_permission.require(http_exception=401)
def add() -> str:
    form = ProductForm()
    return render_template('products/form.html', form=form, edit=False)


@products_bp.route('/edit/<product_id>')
@login_required
@admin_permission.require(http_exception=401)
def edit(product_id: int) -> str:
    item = Product.query.filter_by(id=product_id).one()
    form = ProductForm(
        id=item.id,
        name=item.name,
        ean=item.ean,
        price=item.price,
        visible=item.visible,
        has_alc=item.has_alc,
        is_food=item.is_food,
    )
    return render_template('products/form.html', form=form, edit=True)


@products_bp.route('/delete/<product_id>')
@login_required
@admin_permission.require(http_exception=401)
def delete(product_id: int) -> Response:
    product = Product.query.get(product_id)
    db.session.delete(product)
    db.session.commit()
    flash(f'Deleted product "{product.name}"', category='success')
    return redirect(url_for('admin.products.index'))
