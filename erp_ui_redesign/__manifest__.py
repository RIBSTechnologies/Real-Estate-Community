# -*- coding: utf-8 -*-
{
    'name': 'ERP UI/UX Professional Redesign',
    'version': '20.0.8.0.0',
    'summary': 'Modern Enterprise ERP UI redesign for Purchase, Accounting, and Inventory forms',
    'description': """
        Professional UI/UX Redesign Module for Odoo 18
        ================================================
        Redesigns the following forms with a modern enterprise ERP look:
        - Purchase Order Form
        - Vendor Bill / Invoice Form
        - GRN (Goods Receipt Note) / Stock Picking Form
        - Journal Entry Form
        - Accounting Forms

        Features:
        - Clean responsive 2-column grid layout
        - Modern button styling with hover animations
        - Soft card sections with subtle shadows
        - Professional tab design
        - Improved typography and color system
        - Mobile and tablet responsive design
        - SAP Fiori / Oracle Fusion inspired enterprise styling
        - ERP Documents dashboard (OWL client action)

        Note: This module only improves visual appearance.
        No fields are removed, no business logic is changed.

        v1.2.0 changelog
        ----------------
        * Added: Settings > General Settings > "ERP UI Redesign" block with
          a font picker (Default / Inter / Roboto / System UI / Georgia)
          that applies across every form and list view.
        * Added: a defensive rule so the accent-coloured input border/glow
          only ever shows while a field is actually focused.

        v2.0.0 changelog
        ----------------
        * Added: a Visual Theme picker (Vibrant/3D, Minimal, Classic) next
          to the font picker in the ERP UI Redesign settings popup.
        * Changed: the currency-code alignment fix and the tax-totals link
          underline fix are now applied at runtime in JS with inline
          `!important` styles, instead of relying only on a CSS selector.
          An inline `!important` style beats any external stylesheet
          regardless of load order or specificity, which a plain SCSS
          rule can't guarantee if another installed module's CSS also
          targets the same elements.
        * Fixed: enhancement functions previously located "the" open form
          with `document.querySelector(".o_form_view")` - the first match
          in document order - which could silently miss a wizard/dialog's
          form if it rendered after the background view in the DOM. Now
          scoped across every open form on the page at once.
        * Housekeeping: removed the abandoned `res_config_settings.py` /
          `res_config_settings_views.xml` files from an earlier iteration
          that were left in some installs after files were copied in
          rather than the whole folder being replaced.

        v3.0.0 changelog
        ----------------
        * Added: "ERP Documents" dashboard - an OWL client action under
          ERP UI Redesign > Documents. One screen showing Purchase Orders,
          Vendor Bills, Customer Invoices, Goods Receipts and Journal
          Entries, switched with a pill row, in a styled table with
          coloured status badges. Row click opens the record; New and
          Open List hand off to the normal views. Nothing is stored - it
          reads through the ORM, so record rules and access rights apply
          exactly as they do everywhere else, and a model the user cannot
          read simply drops its tab instead of erroring.
        * Added: `static/src/xml/` and `static/src/css/` alongside the
          existing `scss/` and `js/` folders. SCSS stays where it is: it
          is 1000+ lines of form skinning that has nothing to do with the
          dashboard, and moving it would rewrite every asset path for no
          gain.
        * Added: `.o_erp_fixed_cols` - drop the class on a one2many
          `<list>` and its columns stop reflowing (fixed table layout,
          nowrap + ellipsis, right-aligned numerics, narrow selector
          column). Generalised from a fix that previously had to be
          rewritten per-field for each embedded list.
        * Changed: the "ERP UI Redesign" root menu is no longer
          `groups="base.group_system"`. Appearance Settings under it still
          is; the root had to open up for non-admins to reach the
          dashboard, since a child menu can never outrank its parent.
        * Fixed: the configurable interface font never reached the navbar
          or any dropdown menu. Section 24 named only the form/list/
          control-panel/modal containers, and from Odoo 17 the Dropdown
          component portals its menu panel out into `.o-overlay-container`
          at body level, so no rule scoped under `.o_main_navbar` could
          ever match it. New section 28 names those containers directly.
        * Fixed: menu text drifting between three sizes inside a single
          dropdown. An Odoo menu section header is a Bootstrap
          `.dropdown-header`, which drops font-size to $font-size-sm as a
          Bootstrap default - core navbar.scss adds only `margin-top: 0`
          to it - while its indented children get padding-left and no
          size change at all. Section 28 puts every entry on one scale
          and restyles the header as a deliberate label. Sizes are in
          `em` so they track Odoo's own scale rather than pinning to px.
        * Housekeeping: `models/res_config_settings.py` and
          `views/res_config_settings_views.xml` are now actually deleted.
          The v2.0.0 note above said they were removed, but both files
          were still shipping - dead, since `models/__init__.py` does not
          import the first and the manifest's `data` list does not load
          the second. Left in place they were a trap: the file defines an
          `erp_ui_font_family` field on `res.config.settings` writing to
          the same `ir.config_parameter` key as the real settings model,
          so anyone re-adding the import would get a second, competing
          font picker inside core Settings - the exact problem the
          standalone model was created to avoid.
    """,
    'author': 'WSI Custom',
    'category': 'Tools',
    'depends': [
        'base',
        'web',
        'account',
        'purchase',
        'stock',
        'purchase_requisition',
    ],
    'data': [
        'security/ir.access.csv',
        'views/purchase_order_views.xml',
        'views/account_move_views.xml',
        'views/stock_picking_views.xml',
        # Defines menu_erp_ui_redesign_root - must load before any file
        # that hangs a menuitem off it.
        'views/erp_ui_redesign_settings_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'erp_ui_redesign/static/src/scss/erp_redesign.scss',
            'erp_ui_redesign/static/src/js/erp_ui_enhance.js',
        ],
    },
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'LGPL-3',
}
