from dateutil.relativedelta import relativedelta
from odoo import api, fields, models


class HrEmployeeAnnualLeave(models.Model):
    """CR 2.6 -- how many days of annual leave an employee is entitled to.

    Three tiers, in increasing order of seniority:

      * first year of employment      -> 8 annual days (plus 7 separate casual days)
      * thereafter                    -> 14 days
      * 10 years of INSURED service   -> 30 days

    The last tier is the one the requirement warns about. It is measured
    from ``social_insurance_start_date``, not from the joining date, because
    insured service is portable: an employee who arrives with nine years of
    insured service behind them reaches 30 days in their second year here,
    and the first-year default must not quietly hold them at 8.

    The figures are system parameters, not constants, because they are
    company policy, and HR should not need a code release to change them.
    """

    _inherit = 'hr.employee'

    annual_leave_entitlement = fields.Float(
        string='Annual Leave Entitlement', digits=(4, 1),
        compute='_compute_annual_leave_entitlement',
        help='Company annual leave days for this employee today, given '
             'length of service and insured service.')

    @api.model
    def _annual_leave_params(self):
        get = self.env['ir.config_parameter'].sudo().get_param

        def number(key, default):
            try:
                return float(get(key, default))
            except (TypeError, ValueError):
                return float(default)

        return {
            'first_year_days': number('ibs_hr.annual_leave_first_year_days', 8),
            'standard_days': number('ibs_hr.annual_leave_standard_days', 14),
            'long_service_days': number(
                'ibs_hr.annual_leave_long_service_days', 30),
            'long_service_years': number(
                'ibs_hr.annual_leave_long_service_years', 10),
        }

    def _annual_leave_days(self, on_date=None):
        """Entitlement in days as at ``on_date`` (today by default)."""
        self.ensure_one()
        params = self._annual_leave_params()
        on_date = on_date or fields.Date.context_today(self)

        # Long service wins outright: it is the tier CR 2.6 asks us not to
        # undercut with the first-year default.
        insured_from = self.social_insurance_start_date
        if insured_from:
            insured_years = relativedelta(on_date, insured_from).years
            if insured_years >= params['long_service_years']:
                return params['long_service_days']

        # Without a joining date there is no first year to be inside, so the
        # standard entitlement applies; assuming the reduced one would
        # understate it on the strength of missing data.
        joined = self.joining_date
        if joined and on_date < joined + relativedelta(years=1):
            return params['first_year_days']
        return params['standard_days']

    def _compute_annual_leave_entitlement(self):
        for employee in self:
            employee.annual_leave_entitlement = (
                employee._annual_leave_days() if employee.id else 0.0)
