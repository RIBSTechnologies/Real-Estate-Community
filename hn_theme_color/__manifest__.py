{
    'name': 'Theme Color - Change the Main Color of Odoo (Community)',
    'summary': "Pick any color in Settings: buttons, links, menus and highlights of Odoo Community use it.",
    'description': """
Theme Color
===========
Choose the main color of Odoo in Settings > General Settings > Theme color, with a color
picker or a preset. Buttons, links, the top menu, tabs and highlights follow it. The color is
compiled into Odoo's own stylesheets, exactly like the default color, so every screen uses it.

* Works with Odoo Community, and with enterprise-like themes for Community.
* Reset to the default color in one click; uninstalling the module restores it too.
""",
    'version': '20.0.1.0.0',
    'category': 'Themes/Backend',
    'author': 'Habib Nadir',
    'maintainer': 'Habib Nadir',
    'support': 'nadirhabib96@gmail.com',
    'license': 'LGPL-3',
    'images': ['static/description/banner.png'],
    'depends': ['web', 'base_setup'],
    'data': [
        'data/theme_color_data.xml',
        'views/res_config_settings_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'hn_theme_color/static/src/scss/theme_color.scss',
        ],
    },
    'installable': True,
    'application': False,
}
