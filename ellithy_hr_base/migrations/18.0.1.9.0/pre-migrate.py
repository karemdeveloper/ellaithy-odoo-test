"""Reload the onboarding template so it carries the onboarding image.

Same one-off as 18.0.1.4.0: the template sits in a noupdate block, so the
new image row and the logo fallback only reach an existing database if the
old record is dropped before the data files load. Wording edited by hand in
Settings since then is replaced.
"""
import logging

_logger = logging.getLogger(__name__)

XMLID = ('ellithy_hr_base', 'mail_template_employee_welcome')


def migrate(cr, version):
    if not version:
        return
    cr.execute("""
        SELECT res_id FROM ir_model_data
         WHERE module = %s AND name = %s AND model = 'mail.template'
    """, XMLID)
    row = cr.fetchone()
    if not row:
        return
    cr.execute("DELETE FROM ir_model_data WHERE module = %s AND name = %s", XMLID)
    cr.execute("DELETE FROM mail_template WHERE id = %s", (row[0],))
    _logger.info('Onboarding template %s dropped; reloaded with the image row.', row[0])
