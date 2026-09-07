"""CR 2.1 and CR 2.4 -- data fixes that noupdate records cannot carry.

Both sequence data and existing document rows are outside the reach of a
normal module upgrade, so they are corrected here.
"""
import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version:
        return

    # ---- CR 2.1: drop the EMP prefix from the live sequence ---------------
    cr.execute("""
        UPDATE ir_sequence SET prefix = ''
         WHERE code = 'ellithy.hr.employee.code' AND prefix = 'EMP-'
    """)
    _logger.info("CR 2.1: cleared EMP- prefix on %s sequence(s)", cr.rowcount)

    # ---- CR 2.4: seed copy_type from the retired received flag ------------
    # ASSUMPTION, flagged for HR sign-off: a document previously marked
    # received is recorded as a COPY, because the legacy system captured no
    # original/copy distinction. HR must review originals after go-live.
    cr.execute("""
        UPDATE ellithy_hr_document SET copy_type = 'copy'
         WHERE copy_type IS NULL AND received IS TRUE
    """)
    _logger.info("CR 2.4: seeded copy_type on %s document row(s)", cr.rowcount)
