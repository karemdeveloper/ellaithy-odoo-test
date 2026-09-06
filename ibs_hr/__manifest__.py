{
    'name': 'IBS HR Flow',
    'version': '18.0.1.0.0',
    'summary': 'Payroll input chain: attendance day, discipline, loans, advances and payslip',
    'description': """
IBS HR Flow
===========
Everything that feeds payroll, migrated from the legacy Laravel HR platform.

The chain, in dependency order:

    attendance + leave  ->  ibs.hr.attendance.day  ->+
    violations          ->  ibs.hr.warning         ->+--> ibs.hr.payslip
    loans / advances    ->  instalments            ->+

Component names and arithmetic follow the legacy ``user_payroll_summaries``
table, verified against 9,976 historical payslips.

Rules confirmed against production data
---------------------------------------
* Daily rate is ``base_salary / 30``. Implied day counts resolve to clean
  integers (1, 2, 3, 21, 25) across 3,174 rows.
* ``net = total_allowance - total_deduction`` holds on 9,959 of 9,976 rows.
* Employee social insurance share is 11% of the subscription salary, the
  Egyptian statutory rate.
* Penalty values in ``violation_penalties`` are expressed in DAYS.

Known legacy defects, deliberately not reproduced -- see README.
    """,
    'author': 'ibs',
    'website': 'https://ibs-egy.com/',
    'category': 'Human Resources',
    'license': 'LGPL-3',
    'depends': [
        'ellithy_hr_base',
        'hr_holidays',
    ],
    'data': [
        'security/ibs_hr_security.xml',
        'security/ir.model.access.csv',
        'data/ir_sequence_data.xml',
        'views/ibs_hr_violation_views.xml',
        'views/ibs_hr_admin_penalty_views.xml',
        'views/ibs_hr_admin_penalty_record_views.xml',
        'views/ibs_hr_commission_penalty_views.xml',
        'views/ibs_hr_investigation_views.xml',
        'views/ibs_hr_permission_views.xml',
        'views/hr_leave_views.xml',
        'views/hr_employee_views.xml',
        'views/ibs_hr_warning_views.xml',
        'views/ibs_hr_attendance_day_views.xml',
        'views/ibs_hr_loan_views.xml',
        'views/ibs_hr_payslip_views.xml',
        'views/menus.xml',
    ],
    'icon': '/ibs_hr/static/description/icon.png',
    'installable': True,
    'application': True,
}
