from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install', 'ellithy_hr')
class TestDependantsFromEitherScreen(TransactionCase):
    """One list of relatives, two doors onto it.

    A dependant belongs to the person, so the rows are stored on the
    employee. HR fills them in while filing the contract as often as from
    the employee file, so the contract reaches the same list through a
    writable related field. These check that an edit made from the contract
    lands on the employee rather than being dropped silently -- a readonly
    related field would swallow it without a word.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.employee = cls.env['hr.employee'].create({'name': 'Relatives Probe'})
        cls.contract = cls.env['hr.contract'].create({
            'name': 'Relatives Probe Contract',
            'employee_id': cls.employee.id,
            'wage': 5000.0,
            'date_start': '2026-01-01',
            'state': 'open',
            'medical_insurance_type': 'a',
            'has_medical_relative': True,
        })

    def test_a_relative_added_on_the_contract_lands_on_the_employee(self):
        self.contract.write({'dependant_ids': [(0, 0, {
            'name': 'Wife', 'relation': 'Spouse',
            'medical_insurance_type': 'a', 'card_number': 'MC-1'})]})
        self.assertEqual(self.employee.dependant_ids.mapped('name'), ['Wife'])
        dependant = self.employee.dependant_ids
        self.assertEqual(dependant.employee_id, self.employee)
        self.assertEqual(dependant.card_number, 'MC-1')

    def test_a_relative_added_on_the_employee_shows_on_the_contract(self):
        self.employee.write({'dependant_ids': [(0, 0, {'name': 'Son'})]})
        self.assertEqual(self.contract.dependant_ids.mapped('name'), ['Son'])

    def test_editing_a_relative_from_the_contract_writes_through(self):
        dependant = self.env['ellithy.hr.dependant'].create({
            'employee_id': self.employee.id, 'name': 'Daughter'})
        self.contract.write({'dependant_ids': [
            (1, dependant.id, {'card_number': 'MC-2'})]})
        self.assertEqual(dependant.card_number, 'MC-2')

    def test_removing_a_relative_from_the_contract_removes_the_row(self):
        dependant = self.env['ellithy.hr.dependant'].create({
            'employee_id': self.employee.id, 'name': 'Brother'})
        self.contract.write({'dependant_ids': [(2, dependant.id, 0)]})
        self.assertFalse(dependant.exists())
        self.assertFalse(self.employee.dependant_ids)

    def test_a_relative_filed_from_the_contract_is_still_audited(self):
        """The chatter entry belongs on the employee whichever door was used."""
        before = self.employee.message_ids
        self.contract.write({'dependant_ids': [(0, 0, {'name': 'Mother'})]})
        notes = self.employee.message_ids - before
        self.assertTrue(any('Mother' in note.body for note in notes))

    def test_a_contract_without_an_employee_lists_no_relatives(self):
        """The form hides the list in this state; the field must not raise."""
        bare = self.env['hr.contract'].create({
            'name': 'Unassigned', 'wage': 1000.0, 'date_start': '2026-01-01'})
        self.assertFalse(bare.employee_id)
        self.assertFalse(bare.dependant_ids)
