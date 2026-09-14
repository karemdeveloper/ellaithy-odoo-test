from psycopg2.errors import UniqueViolation

from odoo.tests import tagged
from odoo.tools import mute_logger

from .common import IbsHrPermissionCommon


@tagged('post_install', '-at_install', 'ibs_hr_permission')
class TestPermissionType(IbsHrPermissionCommon):

    def test_seed_data_present(self):
        lateness = self.env.ref('ibs_hr_permission.permission_type_lateness')
        early_leave = self.env.ref('ibs_hr_permission.permission_type_early_leave')
        self.assertEqual(lateness.name, 'Lateness')
        self.assertEqual(early_leave.name, 'Early Leave')

    def test_name_required(self):
        with self.assertRaises(Exception):
            self.env['ibs.hr.permission.type'].create({})

    @mute_logger('odoo.sql_db')
    def test_name_unique(self):
        self.env['ibs.hr.permission.type'].create({'name': 'Custom Type'})
        with self.assertRaises(UniqueViolation):
            self.env['ibs.hr.permission.type'].create({'name': 'Custom Type'})
            self.env.flush_all()

    def test_can_be_deactivated(self):
        custom = self.env['ibs.hr.permission.type'].create({'name': 'Temp Type'})
        custom.active = False
        self.assertFalse(self.env['ibs.hr.permission.type'].search(
            [('id', '=', custom.id)]))
