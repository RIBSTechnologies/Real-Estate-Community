import base64

from odoo import fields, models
from odoo.tools import file_open
from odoo.tools.image import image_data_uri

ARABIC_DIGITS = str.maketrans('0123456789', '٠١٢٣٤٥٦٧٨٩')


class ResCompany(models.Model):
    _inherit = 'res.company'

    lpo_name_en = fields.Char(
        string='Company Name (English)',
        help="Printed under the Arabic name in the Local Purchase Order header. Empty = the company name.")
    lpo_name_ar = fields.Char(
        string='Company Name (Arabic)',
        help="Printed in the centre of the Local Purchase Order header, above the English name.")
    lpo_po_box = fields.Char(string='P.O. Box', help="e.g. 37447")
    lpo_city_en = fields.Char(string='City Line (English)', default='Dubai - U.A.E.')
    lpo_city_ar = fields.Char(string='City Line (Arabic)', default='دبي - ا.ع.م.')
    lpo_header_mark = fields.Image(
        string='Header Mark', max_width=300, max_height=300,
        help="Small mark printed left of the company name (the green leaf by default).")

    def _lpo_header(self):
        """Everything the Local Purchase Order header prints, with the Arabic
        column in Arabic-Indic digits (as on the printed form)."""
        self.ensure_one()
        fax = self.fax if 'fax' in self._fields else ''
        if self.lpo_header_mark:
            mark = self.lpo_header_mark.decode() if isinstance(self.lpo_header_mark, bytes) else self.lpo_header_mark
        else:
            with file_open('purchase_extended/static/img/lpo_leaf.png', 'rb') as image:
                mark = base64.b64encode(image.read()).decode()
        ar = lambda value: (value or '').translate(ARABIC_DIGITS)
        # The printed form shows the names in large type next to the mark, so
        # the names win as soon as they're entered; the company logo is only a
        # fallback for companies without them.
        use_logo = not (self.lpo_name_ar or self.lpo_name_en) and bool(self.logo)
        return {
            'logo': image_data_uri(self.logo) if use_logo else '',
            'name_en': self.lpo_name_en or self.name or '',
            'name_ar': self.lpo_name_ar or '',
            'po_box': self.lpo_po_box or '',
            'po_box_ar': ar(self.lpo_po_box),
            'city_en': self.lpo_city_en or '',
            'city_ar': self.lpo_city_ar or '',
            'phone': self.phone or '',
            'phone_ar': ar(self.phone),
            'fax': fax or '',
            'fax_ar': ar(fax),
            'email': self.email or '',
            'vat': self.vat or '',
            'mark': 'data:image/png;base64,' + mark,
        }
