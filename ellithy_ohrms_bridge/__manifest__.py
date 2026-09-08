{
    'name': 'Ellithy / OpenHRMS Bridge',
    'version': '18.0.1.4.0',
    'summary': 'Ellithy HR policy on the OpenHRMS loan, advance and '
               'resignation models, plus the joining-date conflict fix',
    'description': """
Ellithy / OpenHRMS Bridge
=========================
The only module that depends on both suites, so it is where anything
spanning the two belongs.

Field conflict: ``joining_date``
--------------------------------
Both suites define ``hr.employee.joining_date``:

* ``ellithy_hr_base`` stores it, migrated from the legacy platform for
  1,228 employees.
* ``hr_employee_updation`` computes it as ``min(contract.date_start)`` and
  stores the result.

Without this module the winner depends on module load order, which is not
something to leave to chance. Worse, the compute depends on ``contract_id``,
so the first time anyone gives one of the 1,026 contract-less employees a
contract, their migrated joining date is silently replaced by the contract
start date. This module depends on both, which fixes the load order, and
overrides the compute so it only fills a joining date that is not already
set.

Policy on the OpenHRMS models
-----------------------------
``hr.loan``
    CR 2.15/2.16 -- four eligibility rules (a year of service, twice salary,
    ten instalments, settled inside the financial year), reported together
    rather than one at a time. CR 2.17 -- HR approves, then Finance.

``salary.advance``
    CR 2.18 -- raised by HR, not through self-service. CR 2.19 -- capped at
    what the employee has earned since the 1st of the month.

``hr.resignation``
    CR 2.7 -- one screen, reached from the employee by smart button.
    CR 2.8 -- confirm, endorse, approve. CR 2.9 -- the agreed type wording.
    CR 2.10 -- a clearance checklist, run after approval on the employee's
    actual last working day.

Migration bookkeeping
---------------------
``hr.loan``, ``salary.advance``, ``hr.resignation`` and
``hr.employee.family`` each gain the ``legacy_id`` column the Ellithy models
already carry, so a migration re-run matches rather than duplicates.
    """,
    'author': 'ibs',
    'category': 'Human Resources',
    'license': 'LGPL-3',
    'depends': [
        'ellithy_hr_base',
        'hr_employee_updation',
        'ohrms_loan',
        'ohrms_loan_accounting',
        'ohrms_salary_advance',
        'hr_resignation',
        'hr_attendance',
        'hrms_dashboard',
        'hr_payroll_community',
        'oh_employee_documents_expiry',
        'ibs_hr',
        'hr_training_management',
        'survey',
    ],
    'data': [
        'security/ir.model.access.csv',
        'security/hr_resignation_clearance_security.xml',
        'views/hr_loan_views.xml',
        'views/salary_advance_views.xml',
        'views/hr_resignation_views.xml',
        'wizard/hr_resignation_clearance_wizard_views.xml',
        'views/hr_employee_views.xml',
        'views/menus.xml',
        'views/menu_arrangement.xml',
    ],
    'icon': '/ellithy_ohrms_bridge/static/description/icon.png',
    'installable': True,
    'application': False,
    'auto_install': True,
}
