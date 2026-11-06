# -*- coding: utf-8 -*-
{
    'name': "Preview Attachments (Many2Many)",
    'summary': "Preview attachments (Image, GIF, Video, PDF, TXT) directly from Many2many Binary field",
    'description': """
This widget supports opening a popup to preview files (Image, GIF, Video, PDF, TXT) 
directly from Many2many binary field attachments.
    """,
    'author': "Lucas",
    'website': "https://example.com",
    'category': 'Technical',
    'version': '20.0.1.0',
    'depends': ['base', 'web', 'mail'],
    'assets': {
        'web.assets_backend': [
            '/many2many_binary_field_preview/static/src/many2many_binary_field_preview.xml',
            # '/many2many_binary_field_preview/static/src/css/custom_modal.css',
            '/many2many_binary_field_preview/static/src/many2many_binary_field_preview.js',
        ],
    },
    'images': ['static/description/home.png'],
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
