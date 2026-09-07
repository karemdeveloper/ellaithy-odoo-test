"""Move the remaining exits off hr.employee and onto hr.resignation.

``ellithy_hr_base`` records an exit as three fields on the employee --
``resignation_date``, ``last_working_day`` and ``resignation_type`` -- set
either by the migration from the legacy platform or by the status wizard.
``hr.resignation`` is now the single screen for a resignation (CR 2.7), so
an archived employee whose exit exists only as those fields is invisible
there: no record to open, nothing in the list, and the smart button on their
form leads nowhere.

An earlier pass already created resignations for the employees who had a
full date pair. This one picks up the remainder, which are mostly archived
employees carrying only a last working day.

Idempotent: an employee who already has any resignation is skipped, so
re-running adds nothing.

What is NOT invented
--------------------
* ``resignation_type`` is copied when the employee carries one and left
  blank otherwise. The legacy platform did not record it for these rows and
  guessing between "resigned" and "dismissed" would put a claim on someone's
  file that nothing supports. HR can fill it in; the records are reported
  below so they can be found.
* ``reason`` is required by the model. Where the employee carries no
  departure description, a marker is written that says plainly the reason
  was not recorded, rather than a plausible-sounding invention.
"""
import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)

# ellithy_hr_base's exit vocabulary -> the CR 2.9 wording on hr.resignation.
TYPE_MAP = {
    'resignation': 'resigned',
    'termination_of_service': 'fired',
    'contract_expiration': 'contract_end',
}

NO_REASON_ON_FILE = 'Migrated exit: no reason recorded on the employee file.'


def migrate(cr, version):
    if not version:
        return

    env = api.Environment(cr, SUPERUSER_ID, {})
    Resignation = env['hr.resignation']

    cr.execute("""
        SELECT e.id
          FROM hr_employee e
         WHERE (e.resignation_date IS NOT NULL
                OR e.last_working_day IS NOT NULL)
           AND NOT EXISTS (SELECT 1 FROM hr_resignation r
                            WHERE r.employee_id = e.id)
      ORDER BY e.id
    """)
    employee_ids = [row[0] for row in cr.fetchall()]
    if not employee_ids:
        _logger.info('Resignation migration: nothing left to move.')
        return

    created = 0
    untyped = 0
    skipped = []
    for employee in env['hr.employee'].with_context(
            active_test=False).browse(employee_ids):
        last_day = employee.last_working_day or employee.resignation_date
        if not last_day:
            skipped.append(employee.id)
            continue

        resignation_type = TYPE_MAP.get(employee.resignation_type)
        if not resignation_type and employee.inactive_type == 'termination':
            # The coarser flag still distinguishes a dismissal from a
            # resignation, so it is used where the finer one is missing.
            resignation_type = 'fired'
        elif not resignation_type and employee.inactive_type == 'resignation':
            resignation_type = 'resigned'
        if not resignation_type:
            untyped += 1

        # Created in draft and moved to approved by write: the model's
        # _check_joined_date constraint searches for a confirmed or approved
        # resignation for the employee WITHOUT excluding the record being
        # checked, so creating one directly as approved would refuse itself.
        resignation = Resignation.create({
            'employee_id': employee.id,
            'joined_date': employee.joining_date,
            'expected_revealing_date': last_day,
            'reason': employee.departure_description or NO_REASON_ON_FILE,
            'resignation_type': resignation_type,
        })
        resignation.write({
            'state': 'approved',
            'resign_confirm_date': employee.resignation_date or last_day,
            'approved_revealing_date': last_day,
        })
        created += 1

    _logger.info(
        'Resignation migration: created %s hr.resignation record(s) from '
        'employee exit fields.', created)
    if untyped:
        _logger.warning(
            'Resignation migration: %s of those carry no resignation type, '
            'because the employee record held none. Filter Resignations on '
            'an empty Type to complete them.', untyped)
    if skipped:
        _logger.warning(
            'Resignation migration: skipped %s employee(s) with an exit type '
            'but no usable date: %s', len(skipped), skipped)
