# -*- coding: utf-8 -*-


def migrate(cr, version):
    """The 'Purchase' Payment Type was removed from maintenance requests;
    move any request still on it to the field default ('invoice') - the same
    thing its ondelete='set default' would have done - before the selection
    value is dropped."""
    cr.execute("UPDATE maintenance_request SET payment_type = 'invoice' WHERE payment_type = 'purchase'")
