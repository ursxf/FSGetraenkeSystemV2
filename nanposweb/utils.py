import tempfile

import qrcode
from flask import Blueprint, render_template, current_app, send_file, redirect, url_for

from .forms import QRCodeForm

utils_bp = Blueprint('utils', __name__, url_prefix='/utils')


@utils_bp.route('/qrcode')
def qr():
    form = QRCodeForm()
    return render_template('utils/qrcode.html', form=form)


@utils_bp.route('/qrcode/download', methods=['POST'])
def download():
    form = QRCodeForm()

    if form.validate_on_submit():
        with tempfile.NamedTemporaryFile(dir=current_app.root_path) as qrcode_file:
            qr_img = qrcode.make(f'{form.username.data}\n{form.pin.data}')
            qr_img.save(qrcode_file)

            if form.download_png.data:
                return send_file(qrcode_file.name, as_attachment=True, attachment_filename='qrcode.png')
            elif form.download_pass.data:
                return redirect(url_for('utils.qr'))
