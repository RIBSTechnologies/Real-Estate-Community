from odoo import models


class PurchaseOrderLine(models.Model):
    """Analytic distribution must never block a purchase, same business rule
    as invoice/bill lines (al_shafar_extended AccountMoveLine): the user may
    tag a line with any subset of the plans (Property Type, Sub Type,
    Building, Units, Cost Center, ...) or none, without Odoo's
    "One or more lines require a 100% analytic distribution." check on
    RFQ/PO confirmation."""
    _inherit = 'purchase.order.line'

    def _validate_distribution(self, **kwargs):
        return


class PurchaseRequestLine(models.Model):
    _inherit = 'purchase.request.line'

    def _validate_distribution(self, **kwargs):
        return
