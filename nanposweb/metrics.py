from math import log
from flask import Blueprint, Response
from prometheus_client import CONTENT_TYPE_LATEST, Gauge, generate_latest

from nanposweb.db.helpers import count_revenues_by_product, get_products, total_balance

metrics_bp = Blueprint('metrics', __name__)

revenue_gauge = Gauge('nanposweb_revenue', 'Number of revenue per product', ['product_id', 'product_name'])
balance_total_gauge = Gauge('nanposweb_balance_total', 'Total balance of all users in cents')


def update_metrics():
    products = get_products()
    for product in products:
        revenues = count_revenues_by_product(product.id)
        revenue_gauge.labels(product.id, product.name).set(revenues)

    balance_total_gauge.set(total_balance())


@metrics_bp.route('/metrics', methods=['GET'])
def metrics() -> Response:
    update_metrics()
    return Response(generate_latest(), mimetype=CONTENT_TYPE_LATEST)
