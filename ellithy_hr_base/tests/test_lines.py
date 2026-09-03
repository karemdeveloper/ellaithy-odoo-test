from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install', 'ellithy_hr')
class TestCompanyLine(TransactionCase):
    """One model behind five menus, so the type must police its own holder."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.branch = cls.env['ellithy.branch'].create({
            'name': 'Line Branch', 'company_id': cls.env.company.id})
        cls.directorate = cls.env['hr.department'].create({
            'name': 'Line Directorate', 'dept_type': 'directorate',
            'branch_id': cls.branch.id})
        cls.section = cls.env['hr.department'].create({
            'name': 'Line Section', 'dept_type': 'section',
            'parent_id': cls.directorate.id})
        cls.employee = cls.env['hr.employee'].create({
            'name': 'Line Holder', 'branch_id': cls.branch.id})

    def _line(self, **kwargs):
        values = {'number': '01000000001', 'line_type': 'phone'}
        values.update(kwargs)
        return self.env['ellithy.hr.line'].create(values)

    def test_phone_is_held_by_an_employee(self):
        line = self._line(employee_id=self.employee.id)
        self.assertEqual(line.holder_type, 'employee')
        self.assertEqual(line.holder_name, self.employee.display_name)

    def test_adsl_is_held_by_a_department(self):
        line = self._line(number='0220000001', line_type='adsl',
                          department_id=self.directorate.id)
        self.assertEqual(line.holder_type, 'department')

    def test_data_is_held_by_a_section(self):
        line = self._line(number='0230000001', line_type='data',
                          section_id=self.section.id)
        self.assertEqual(line.holder_type, 'section')

    def test_wrong_holder_for_the_type_is_rejected(self):
        with self.assertRaises(ValidationError):
            self._line(number='0240000001', line_type='adsl',
                       employee_id=self.employee.id)
        with self.assertRaises(ValidationError):
            self._line(number='0250000001', line_type='phone',
                       department_id=self.directorate.id)

    def test_same_number_allowed_across_types(self):
        """A phone and an ADSL line may share a number; two phones may not."""
        self._line(number='01099999999', line_type='phone',
                   employee_id=self.employee.id)
        self._line(number='01099999999', line_type='adsl',
                   department_id=self.directorate.id)
        with self.assertRaises(Exception):
            self._line(number='01099999999', line_type='phone',
                       employee_id=self.employee.id)
            self.env.flush_all()

    def test_line_is_searchable_by_serial_and_bundle(self):
        line = self._line(number='01011112222', serial='8920022023013429839',
                          bundle='2025 Business Flex 150',
                          employee_id=self.employee.id)
        Line = self.env['ellithy.hr.line']
        self.assertIn(line.id, [r[0] for r in Line.name_search('892002202301')])
        self.assertIn(line.id, [r[0] for r in Line.name_search('Flex 150')])

    def test_display_name_shows_the_type(self):
        line = self._line(number='01033334444', employee_id=self.employee.id)
        self.assertIn('Work Number', line.display_name)

    def test_unassigned_line_is_valid(self):
        """A spare SIM still costs money and must be recordable."""
        line = self._line(number='01055556666')
        self.assertFalse(line.employee_id)
        self.assertFalse(line.holder_name)
