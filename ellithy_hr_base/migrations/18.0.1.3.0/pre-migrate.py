"""Move insurance from the employee onto the contract.

Both insurances are terms of an engagement -- the tier and its costs, the
office an employee is registered at, the subscription salary a contribution
is calculated on. Held on the employee, renewing a contract silently rewrote
the figures the previous one was filed under.

The columns are added by the ORM on this same upgrade, but the employee's
fields become RELATED at the moment the new model loads, which drops their
columns. So the copy has to happen in a pre-migration, while both sides still
exist as plain columns.

Copied onto the employee's most recent contract. An employee with several
contracts gets the values on the latest one only; the older ones stay empty
rather than being back-filled with figures that were never theirs.
"""
import logging

_logger = logging.getLogger(__name__)

FIELDS = [
    'has_social_insurance',
    'social_insurance_office_id',
    'social_insurance_number',
    'social_insurance_start_date',
    'medical_insurance_type',
    'medical_insurance_date',
    'medical_card_number',
    'medical_cost_per_year',
    'medical_cost_per_month',
    'medical_employee_share',
    'has_medical_relative',
    'insurance_number',
    'insurance_office',
    'insurance_entered_date',
    'insurance_salary',
    'social_insurance_price',
]


def _column_exists(cr, table, column):
    cr.execute("""
        SELECT 1 FROM information_schema.columns
         WHERE table_name = %s AND column_name = %s
    """, (table, column))
    return bool(cr.fetchone())


def migrate(cr, version):
    if not version:
        return

    movable = [f for f in FIELDS
               if _column_exists(cr, 'hr_employee', f)]
    if not movable:
        _logger.info('Insurance migration: nothing on hr_employee to move.')
        return

    # Add the destination columns up front. The ORM would create them later
    # in this same upgrade, but the copy below runs first.
    types = {
        'has_social_insurance': 'boolean',
        'has_medical_relative': 'boolean',
        'social_insurance_office_id': 'integer',
        'social_insurance_number': 'varchar',
        'social_insurance_start_date': 'date',
        'medical_insurance_type': 'varchar',
        'medical_insurance_date': 'date',
        'medical_card_number': 'varchar',
        'medical_cost_per_year': 'numeric',
        'medical_cost_per_month': 'numeric',
        'medical_employee_share': 'double precision',
        'insurance_number': 'varchar',
        'insurance_office': 'varchar',
        'insurance_entered_date': 'date',
        'insurance_salary': 'numeric',
        'social_insurance_price': 'numeric',
    }
    for name in movable:
        cr.execute(
            'ALTER TABLE hr_contract ADD COLUMN IF NOT EXISTS "%s" %s'
            % (name, types[name]))

    assignments = ', '.join('"%s" = e."%s"' % (f, f) for f in movable)
    cr.execute("""
        UPDATE hr_contract c
           SET %s
          FROM hr_employee e
         WHERE e.id = c.employee_id
           AND c.id = (SELECT c2.id FROM hr_contract c2
                        WHERE c2.employee_id = e.id
                     ORDER BY c2.date_start DESC NULLS LAST, c2.id DESC
                        LIMIT 1)
    """ % assignments)
    _logger.info(
        'Insurance migration: copied %s field(s) onto %s contract(s).',
        len(movable), cr.rowcount)

    # Anyone carrying insurance with no contract to carry it: the values are
    # about to become unreachable, so say who they are rather than lose them
    # quietly.
    cr.execute("""
        SELECT e.id, e.name
          FROM hr_employee e
         WHERE (e.has_social_insurance IS TRUE
                OR e.social_insurance_number IS NOT NULL
                OR e.medical_insurance_type IS NOT NULL)
           AND NOT EXISTS (SELECT 1 FROM hr_contract c
                            WHERE c.employee_id = e.id)
    """)
    stranded = cr.fetchall()
    if stranded:
        _logger.warning(
            'Insurance migration: %s employee(s) hold insurance but have no '
            'contract, so their values could not be moved and are no longer '
            'reachable from the employee form. Create a contract and re-enter '
            'them: %s',
            len(stranded), ', '.join('%s (id %s)' % (n, i) for i, n in stranded))
