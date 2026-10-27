"""Replace the onboarding template with the redesigned one.

The template is declared inside ``<data noupdate="1">`` so that wording HR
adjusts in Settings survives an upgrade. That is the right default, and it
is also why the CR 2.5 redesign -- the company logo, the orange and white
layout, the subject naming the joiner -- could not reach a database that
already had the old record: noupdate means "create once, never touch again".

Dropping the record and its external ID here, before the data files load,
lets the new definition be created fresh. Every later upgrade leaves it
alone again, so this is a one-off for the redesign.

Any wording edited by hand in Settings before this upgrade is replaced. That
is the intended trade for shipping the new design; there was no hand-editing
to preserve, because until now the template was only ever sent automatically.
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
        _logger.info('CR 2.5: no existing onboarding template to replace.')
        return

    template_id = row[0]
    cr.execute("DELETE FROM ir_model_data WHERE module = %s AND name = %s",
               XMLID)
    cr.execute("DELETE FROM mail_template WHERE id = %s", (template_id,))
    _logger.info(
        'CR 2.5: dropped onboarding template %s so the redesigned one is '
        'loaded in its place.', template_id)
