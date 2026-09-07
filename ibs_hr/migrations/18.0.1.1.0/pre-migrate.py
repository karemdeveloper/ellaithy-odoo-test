"""Withdraw ibs.hr.payslip and ibs.hr.loan in favour of the standard models.

``ibs_hr_warning.payslip_id`` and ``ibs_hr_admin_penalty_record.payslip_id``
still point at ``hr.payslip`` by name, but the integers in those columns are
``ibs_hr_payslip`` primary keys. Left alone they would silently resolve to
unrelated standard payslips, so they are cleared before the new foreign key
constraint is built.

The withdrawn tables themselves are deliberately NOT dropped: they hold
migrated history, and dropping them is a decision for whoever is running the
upgrade, not a side effect of it. The row counts are logged so that decision
can be made with the numbers in hand.
"""
import logging

_logger = logging.getLogger(__name__)

WITHDRAWN_TABLES = ('ibs_hr_payslip', 'ibs_hr_loan_line', 'ibs_hr_loan')

STALE_REFERENCES = (
    ('ibs_hr_warning', 'payslip_id'),
    ('ibs_hr_admin_penalty_record', 'payslip_id'),
)


def _table_exists(cr, table):
    cr.execute("SELECT to_regclass(%s)", (table,))
    return cr.fetchone()[0] is not None


def migrate(cr, version):
    if not version:
        return

    for table, column in STALE_REFERENCES:
        if not _table_exists(cr, table):
            continue
        cr.execute(
            f'UPDATE {table} SET {column} = NULL WHERE {column} IS NOT NULL')
        _logger.info(
            'Cleared %s stale %s.%s reference(s) to the withdrawn '
            'ibs.hr.payslip', cr.rowcount, table, column)
        # The old constraint names the withdrawn table; the ORM builds the
        # replacement against hr_payslip once the column is empty.
        cr.execute(
            f'ALTER TABLE {table} DROP CONSTRAINT IF EXISTS '
            f'{table}_{column}_fkey')

    for table in WITHDRAWN_TABLES:
        if not _table_exists(cr, table):
            continue
        cr.execute(f'SELECT count(*) FROM {table}')
        _logger.warning(
            'Table %s holds %s row(s) and is no longer backed by a model. '
            'It is left in place; drop it manually once the data has been '
            'reconciled against hr_payslip / hr_loan.',
            table, cr.fetchone()[0])
