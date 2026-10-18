{
    'name': 'IBS HR Flow',
    'version': '18.0.1.4.0',
    'summary': 'Attendance days, discipline and the penalty deduction ledger '
               'that feeds the standard payslip',
    'description': """
IBS HR Flow
===========
The attendance and discipline records that feed payroll, migrated from the
legacy Laravel HR platform.

    attendance + leave  ->  ibs.hr.attendance.day  ->+
    violations          ->  ibs.hr.warning         ->+--> hr.payslip

Payroll itself is ``hr_payroll_community``. The custom ``ibs.hr.payslip``
engine and ``ibs.hr.loan`` model were withdrawn in 18.0.1.1.0 in favour of
the standard ``hr.payslip``, ``hr.loan`` and ``salary.advance`` models; the
loan and advance policy rules now live in ``ellithy_ohrms_bridge``. Hourly
permission requests and field missions moved out to ``ibs_hr_permission`` in
18.0.1.3.0: that model was a legacy-migration target (``legacy_id``, ``kind``
telling Permission and Mission apart in one table); the replacement is a
clean, non-legacy model with its own configuration and no dependency on this
module.

What this module still owns
---------------------------
* ``ibs.hr.attendance.day`` -- the daily attendance roll-up.
* The discipline ladder: ``ibs.hr.violation`` and ``ibs.hr.warning``.
* ``ibs.hr.warning.deduction`` -- the ledger enforcing CR 2.12's five-day
  monthly ceiling, with the remainder carried into following months.
* Administrative, commission and investigation records.

Rules confirmed against production data
---------------------------------------
* Daily rate is ``base_salary / 30``. Implied day counts resolve to clean
  integers (1, 2, 3, 21, 25) across 3,174 rows.
* Penalty values in ``violation_penalties`` are expressed in DAYS.

Known legacy defects, deliberately not reproduced -- see README.
    """,
    'author': 'ibs',
    'website': 'https://ibs-egy.com/',
    'category': 'Human Resources',
    'license': 'LGPL-3',
    'depends': [
        'ellithy_hr_base',
        'hr_payroll_community',
    ],
    'data': [
        'security/ibs_hr_security.xml',
        'security/groups.xml',
        'security/ir.model.access.csv',
        'data/ir_sequence_data.xml',
        'data/mail_template_data.xml',
        'data/hr_salary_rule_data.xml',
        'views/ibs_hr_violation_views.xml',
        'views/ibs_hr_admin_penalty_views.xml',
        'views/ibs_hr_admin_penalty_record_views.xml',
        'views/ibs_hr_commission_penalty_views.xml',
        'views/ibs_hr_investigation_views.xml',
        'views/hr_employee_views.xml',
        'views/ibs_hr_warning_views.xml',
        'views/hr_payslip_views.xml',
        'views/ibs_hr_attendance_day_views.xml',
        'views/menus.xml',
    ],
    'icon': '/ibs_hr/static/description/icon.png',
    'installable': True,
    'application': True,
}
