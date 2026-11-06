# -*- coding: utf-8 -*-

import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """property.project.land_area was first deployed as a Float (creating
    a `double precision` column), then changed to a Char - Odoo's own
    automatic column-type migration can't cleanly convert an existing
    `double precision` column to text on its own (it errors with "column
    land_area is of type double precision but expression is of type
    character varying" while trying to write the converted value back
    without an explicit cast).

    Runs as a pre-migrate (before Odoo's field setup/_auto_init attempts
    its own conversion) so the column is already the right type by the
    time Odoo gets to it - a plain SQL ALTER with an explicit USING cast,
    which numeric-to-text always succeeds at (unlike the reverse, this
    direction can't lose data or fail to parse).
    """
    cr.execute("""
        SELECT data_type FROM information_schema.columns
        WHERE table_name = 'property_project' AND column_name = 'land_area'
    """)
    row = cr.fetchone()
    if not row:
        return  # column doesn't exist yet - nothing to fix
    if row[0] == 'character varying' or row[0] == 'text':
        return  # already the right type (e.g. a fresh database)

    _logger.info("land_area column is %s, converting to varchar", row[0])
    cr.execute("""
        ALTER TABLE property_project
        ALTER COLUMN land_area TYPE varchar USING land_area::varchar
    """)
