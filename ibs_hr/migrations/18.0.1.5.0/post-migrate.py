"""HR letter item 24: link the existing free-text reasons to the new list."""
from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    Reason = env['ibs.hr.commission.penalty.reason']
    penalties = env['ibs.hr.commission.penalty'].with_context(
        active_test=False).search([('reason_id', '=', False)])
    for text in set(penalties.mapped('reason')):
        reason = Reason._from_text(text or 'Unspecified')
        # SQL, so locked (approved) penalties keep their status and tracking.
        cr.execute(
            "UPDATE ibs_hr_commission_penalty SET reason_id = %s "
            "WHERE reason_id IS NULL AND COALESCE(reason, '') = %s",
            [reason.id, text or ''])
