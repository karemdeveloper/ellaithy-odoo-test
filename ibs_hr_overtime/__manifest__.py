{
    'name': 'IBS HR Overtime',
    'version': '18.0.1.3.0',
    'summary': 'Shift-derived overtime approval and compensatory rest',
    'author': 'ibs',
    'website': 'https://ibs-egy.com/',
    'category': 'Human Resources',
    'license': 'LGPL-3',
    'depends': [
        'ibs_hr_shift',
        'ibs_hr_time_off',
    ],
    'data': [
        'security/groups.xml',
        'security/ibs_hr_overtime_security.xml',
        'security/ir.model.access.csv',
        'data/ir_cron_data.xml',
        'views/ibs_hr_overtime_views.xml',
        'views/menus.xml',
    ],
    'installable': True,
}
