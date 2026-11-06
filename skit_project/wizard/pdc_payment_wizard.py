# -*- coding: utf-8 -*-
# imports of odoo
from odoo import models


class PDCWizard(models.Model):
    _inherit = "pdc.wizard"
    
    def action_deposited(self):
        """ extend method to update analytic distribution in pdc deposit"""
        tenancy_property_id = self.invoice_id.tenancy_property_id or self.invoice_id.maintenance_request_id.property_id
        return super(
            PDCWizard,
            self.with_context(tenancy_id=tenancy_property_id)
        ).action_deposited()
        
    def action_done(self):
        """ extend method to update analytic distribution in pdc done"""
        tenancy_property_id = self.invoice_id.tenancy_property_id or self.invoice_id.maintenance_request_id.property_id
        return super(
            PDCWizard,
            self.with_context(tenancy_id=tenancy_property_id)
        ).action_done()