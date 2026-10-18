{
    'name': 'Excel Attendance Import',
    'version': '18.0.1.0.2',
    'license': 'LGPL-3',
    'category': 'Human Resources/Attendances',
    'depends': ['hr_attendance'],
    'external_dependencies': {'python': ['openpyxl']},
    'data': ['security/security.xml', 'security/ir.model.access.csv',
             'views/import_views.xml', 'views/wizard_views.xml'],
    'installable': True,
}
