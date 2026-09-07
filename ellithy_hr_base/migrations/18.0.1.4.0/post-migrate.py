"""Close the onboarding mail off for everyone who already exists.

The welcome mail became a button (CR 2.5, revised). The button shows while
``welcome_email_sent`` is false -- which, on the morning of the upgrade, is
every one of the 1,230 employees already on file, including the ones who
left years ago.

Marking them as already sent is not a claim that a mail went out. It is the
only reading that keeps the button meaning what it says: "this joiner has not
been welcomed yet". The alternative is a button offering to welcome the
entire company to a job they have held for a decade.

The stored timestamp is deliberately left empty, so a record shows "sent"
with no date and is recognisable as pre-existing rather than mailed.
"""
import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version:
        return

    cr.execute("""
        UPDATE hr_employee
           SET welcome_email_sent = TRUE
         WHERE welcome_email_sent IS NOT TRUE
    """)
    _logger.info(
        'CR 2.5: marked %s existing employee(s) as already onboarded, so the '
        'Send Onboarding Mail button only appears for new joiners.',
        cr.rowcount)

    # The parameter that used to switch the automatic send on and off has no
    # meaning now that sending is a deliberate act.
    cr.execute(
        "DELETE FROM ir_config_parameter WHERE key = 'ellithy_hr.send_welcome_email'")
    if cr.rowcount:
        _logger.info('CR 2.5: removed the obsolete send_welcome_email switch.')
