from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase, tagged

COLOR = '#0e7490'


@tagged('post_install', '-at_install')
class TestThemeColor(TransactionCase):

    def _save(self, **vals):
        settings = self.env['res.config.settings'].create(vals)
        return settings.execute()

    def _backend_css(self):
        # save and reset share one transaction here (same write_date): drop the compiled bundles
        self.env['ir.attachment'].search([('url', '=like', '/web/assets/%')]).unlink()
        self.env.transaction.invalidate_ormcache('assets')  # Odoo 20 API
        bundle = self.env['ir.qweb']._get_asset_bundle('web.assets_backend', css=True, js=False)
        return bundle.css().raw.content.decode()

    def test_color_compiled_into_the_stylesheets(self):
        action = self._save(hn_theme_color=COLOR)
        self.assertEqual(action, {'type': 'ir.actions.client', 'tag': 'reload'}, "the page reloads to load the new colors")
        scss = self.env.ref('hn_theme_color.theme_color_scss').raw.content.decode()
        self.assertIn(f'$o-brand-primary: {COLOR};', scss)
        css = self._backend_css().lower()
        self.assertIn(COLOR, css)
        self.assertGreater(css.count(COLOR), 100)
        # the only default purple left is a color Odoo writes directly: a more specific rule overrides it
        self.assertLessEqual(css.count('#71639e'), 1)
        self.assertIn(f'body .o-we-tablepicker .o-we-cell.active{{background-color: {COLOR}', css)
        # reset: Odoo's default color again
        self.env['res.config.settings'].create({}).action_hn_theme_color_reset()
        css = self._backend_css().lower()
        self.assertNotIn(COLOR, css)
        self.assertIn('#71639e', css)

    def test_preset_and_validation(self):
        settings = self.env['res.config.settings'].new({'hn_theme_color_preset': '#b91c1c'})
        settings._onchange_hn_theme_color_preset()
        self.assertEqual(settings.hn_theme_color, '#b91c1c')
        with self.assertRaises(ValidationError):
            self.env['res.config.settings'].create({'hn_theme_color': 'red; } body { display: none'})
