from flask import Blueprint, render_template

blueprint = Blueprint('example', __name__, template_folder='templates')


def get_utils():
    return [('example.helloworld', 'Example module')]


@blueprint.route('/example', methods=['GET'])
def helloworld():
    return render_template('example.html')
