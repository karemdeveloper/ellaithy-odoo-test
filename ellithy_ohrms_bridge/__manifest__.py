{
    'name': 'Ellithy / OpenHRMS Bridge',
    'version': '18.0.1.0.0',
    'summary': 'Resolves field conflicts between the Ellithy HR modules and '
               'the Cybrosys OpenHRMS suite',
    'description': """
Ellithy / OpenHRMS Bridge
=========================
Both suites define ``hr.employee.joining_date``:

* ``ellithy_hr_base`` stores it, migrated from the legacy platform for
  1,228 employees.
* ``hr_employee_updation`` computes it as ``min(contract.date_start)`` and
  stores the result.

Without this module the winner depends on module load order, which is not
something to leave to chance. Worse, the compute depends on ``contract_id``,
so the first time anyone gives one of the 1,026 contract-less employees a
contract, their migrated joining date is silently replaced by the contract
start date.

This module depends on both, which fixes the load order, and overrides the
compute so it only fills a joining date that is not already set. Existing
values survive; new employees still get the OpenHRMS behaviour.
    """,
    'author': 'ibs',
    'category': 'Human Resources',
    'license': 'LGPL-3',
    'depends': [
        'ellithy_hr_base',
        'hr_employee_updation',
        'ohrms_loan',
        'ohrms_salary_advance',
        'hr_resignation',
    ],
    'data': [],
    'installable': True,
    'application': False,
    'auto_install': True,
}
