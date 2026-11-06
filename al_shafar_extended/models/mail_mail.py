# -*- coding: utf-8 -*-

import logging

from odoo import models

_logger = logging.getLogger(__name__)


class MailMail(models.Model):
    _inherit = 'mail.mail'

    def _test_email_addresses(self):
        """Every email address this mail.mail touches - sender
        (email_from) as well as recipients (email_to/email_cc, plus
        recipient_ids' resolved emails). A test/placeholder '@test' marker
        can end up on either side (e.g. the company/landlord's own
        outgoing address, not just the tenant's), so both need checking."""
        self.ensure_one()
        emails = []
        for field in ('email_from', 'email_to', 'email_cc'):
            value = getattr(self, field) or ''
            emails.extend(part.strip() for part in value.split(',') if part.strip())
        emails.extend(self.recipient_ids.mapped('email'))
        return [e for e in emails if e]

    def _is_test_email_blocked(self):
        """True if the sender OR any recipient address contains 'test'
        anywhere in it - some seed/demo data carries emails deliberately
        marked with the word 'test' (as a suffix like 'name@domain.com@test',
        with a stray space like 'name@domain.com @test', or any other
        placement) meant to keep test contracts/records from ever emailing
        a real inbox. That marker isn't reliably enforced anywhere else:
        neither Odoo nor every outgoing/receiving mail server validates
        the address strictly enough to always refuse to send it - such an
        address was delivered anyway. This is the actual backstop: block
        the send outright, at the one place every mail.mail record goes
        through before reaching SMTP - covers every mail sent anywhere in
        Odoo (any template, any module), rather than depending on each
        individual send_mail() call site (active_contract.py, rent-
        approval emails, etc.) to check for it itself."""
        self.ensure_one()
        return any('test' in email.lower() for email in self._test_email_addresses())

    def send(self, auto_commit=False, raise_exception=False, post_send_callback=None):
        blocked = self.filtered(lambda m: m._is_test_email_blocked())
        if blocked:
            for mail in blocked:
                _logger.warning(
                    "mail.mail %s: blocked - an address on this mail contains 'test' (%s)",
                    mail.id, mail._test_email_addresses())
            blocked.write({
                'state': 'cancel',
                'failure_reason': 'Blocked: an address on this mail contains "test"',
            })
        remaining = self - blocked
        if not remaining:
            return True
        return super(MailMail, remaining).send(
            auto_commit=auto_commit, raise_exception=raise_exception,
            post_send_callback=post_send_callback)
