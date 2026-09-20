{
    'name': 'IBS HR Public Holidays',
    'version': '18.0.1.1.0',
    'summary': 'Company public holiday dates for HCM attendance',
    'author': 'ibs',
    'website': 'https://ibs-egy.com/',
    'category': 'Human Resources',
    'license': 'LGPL-3',
    'depends': ['ellithy_hr_base'],
    'data': [
        'security/ibs_hr_holiday_security.xml',
        'security/ir.model.access.csv',
        'views/ibs_hr_public_holiday_views.xml',
        'views/menus.xml',
    ],
    'installable': True,
}
