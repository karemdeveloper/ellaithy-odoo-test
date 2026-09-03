from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install', 'ellithy_hr')
class TestJoiningDateBridge(TransactionCase):
    """The migrated joining date must survive contact with OpenHRMS."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.branch = cls.env['ellithy.branch'].create({
            'name': 'Bridge Branch', 'company_id': cls.env.company.id})

    def _employee(self, **kwargs):
        values = {'name': 'Bridge Probe', 'branch_id': self.branch.id}
        values.update(kwargs)
        return self.env['hr.employee'].create(values)

    def _contract(self, employee, date_start):
        return self.env['hr.contract'].create({
            'name': 'Bridge Contract', 'employee_id': employee.id,
            'wage': 1000.0, 'date_start': date_start, 'state': 'open'})

    def test_migrated_date_survives_a_new_contract(self):
        """The exact failure this module exists to prevent."""
        employee = self._employee(joining_date='2019-05-01')
        self._contract(employee, '2024-01-01')
        employee.invalidate_recordset(['joining_date'])
        self.assertEqual(str(employee.joining_date), '2019-05-01')

    def test_empty_date_is_filled_from_the_contract(self):
        """OpenHRMS behaviour still applies where there is nothing to lose."""
        employee = self._employee()
        self.assertFalse(employee.joining_date)
        self._contract(employee, '2024-01-01')
        employee.invalidate_recordset(['joining_date'])
        self.assertEqual(str(employee.joining_date), '2024-01-01')

    def test_earliest_contract_wins_when_deriving(self):
        """The earlier contract has to be closed before the later one opens --
        hr_contract refuses two running contracts at once."""
        employee = self._employee()
        first = self._contract(employee, '2022-06-01')
        first.date_end = '2023-12-31'
        self._contract(employee, '2024-01-01')
        employee.invalidate_recordset(['joining_date'])
        self.assertEqual(str(employee.joining_date), '2022-06-01')

    def test_field_is_still_editable_by_hand(self):
        employee = self._employee(joining_date='2020-01-01')
        employee.joining_date = '2021-02-02'
        self.assertEqual(str(employee.joining_date), '2021-02-02')

    def test_no_contract_leaves_it_empty(self):
        self.assertFalse(self._employee().joining_date)
