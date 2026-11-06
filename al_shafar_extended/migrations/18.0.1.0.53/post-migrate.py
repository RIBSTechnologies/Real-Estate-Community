# -*- coding: utf-8 -*-


def migrate(cr, version):
    """maintenance.product.line now records the invoice / bill it was put on
    (invoice_id / bill_id) so Create Invoice / Create Bill only pick up lines
    not billed yet. Lines of requests invoiced/billed before that all went on
    the request's single invoice_id / bill_id - link them to it, or they'd be
    offered for billing a second time."""
    cr.execute("""
        UPDATE maintenance_product_line line
           SET invoice_id = request.invoice_id
          FROM maintenance_request request
         WHERE line.maintenance_id = request.id
           AND request.invoice_state
           AND request.invoice_id IS NOT NULL
           AND line.invoice_id IS NULL
    """)
    cr.execute("""
        UPDATE maintenance_product_line line
           SET bill_id = request.bill_id
          FROM maintenance_request request
         WHERE line.maintenance_id = request.id
           AND request.bill_state
           AND request.bill_id IS NOT NULL
           AND line.bill_id IS NULL
    """)
