{
    'name': 'IBS HR Permission',
    'version': '18.0.1.2.0',
    'summary': 'Hourly permission requests (lateness / early leave) and field '
               'missions, with admin-configurable types and monthly cap',
    'description': """
IBS HR Permission
==================
A purpose-built replacement for the old combined permission/mission model in
``ibs_hr``. Unlike that model, this one is not a legacy-migration target: it
carries no ``legacy_id`` and depends on nothing but ``ellithy_hr_base``.

Provides
--------
* ``ibs.hr.permission.type`` -- admin-configurable catalogue of permission
  types (seeded with Lateness and Early Leave).
* ``ibs.hr.permission`` -- an hourly permission request: pick a type and a
  duration from a fixed 30/60/90/120-minute list. The request date must be
  yesterday, today or tomorrow (HR Admins may override), and the total
  granted per employee per calendar month is capped (default 4 hours,
  configurable in Settings without a code change).
* ``ibs.hr.mission`` -- a field mission timed by GPS check-in/check-out (or
  a manually entered time span via ``custom_hours``), needing a branch
  manager's approval before HR's, split out of the same legacy table.

Both request models share only generic submit/cancel/reset plumbing and a
reason field via an abstract mixin; the business rules (duration picker and
monthly cap for Permission, timing/approval/admin remark for Mission) are
not shared, by design -- see the module README.
    """,
    'author': 'ibs',
    'website': 'https://ibs-egy.com/',
    'category': 'Human Resources',
    'license': 'LGPL-3',
    'depends': [
        'ellithy_hr_base',
    ],
    'data': [
        'security/groups.xml',
        'security/ibs_hr_permission_security.xml',
        'security/ir.model.access.csv',
        'data/ir_sequence_data.xml',
        'data/ibs_hr_permission_type_data.xml',
        'views/ibs_hr_permission_type_views.xml',
        'views/ibs_hr_permission_views.xml',
        'views/ibs_hr_mission_views.xml',
        'views/res_config_settings_views.xml',
        'views/menus.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'ibs_hr_permission/static/src/js/mission_geo_button.js',
            'ibs_hr_permission/static/src/xml/mission_geo_button.xml',
        ],
    },
    'installable': True,
    'application': False,
}
