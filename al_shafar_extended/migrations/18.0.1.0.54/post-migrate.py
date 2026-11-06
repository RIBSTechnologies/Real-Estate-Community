# -*- coding: utf-8 -*-


def migrate(cr, version):
    """Included Products is now split into Invoice / Vendor Bill / Internal
    Transfer tabs by maintenance.product.line.line_type (new, defaulted to
    'invoice'). Lines that were only ever put on a vendor bill belong on the
    Vendor Bill tab."""
    cr.execute("""
        UPDATE maintenance_product_line
           SET line_type = 'bill'
         WHERE bill_id IS NOT NULL
           AND invoice_id IS NULL
    """)
    # Payment From now drives Payment Type (Customer -> Invoice, Vendor -> Bill).
    cr.execute("""
        UPDATE maintenance_request
           SET payment_type = CASE payment_from WHEN 'customer' THEN 'invoice' ELSE 'bill' END
         WHERE payment_from IN ('customer', 'vendor')
    """)
