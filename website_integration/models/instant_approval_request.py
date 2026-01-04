from odoo import models, fields, api
from odoo.exceptions import ValidationError


class InstantApprovalRequest(models.Model):
    _name = "instant.approval.request"
    _description = "Model For Instant Approval Request"
    _inherit = 'sequence.mixin'
    _sequence_code = 'instant.approval.request'
    full_name = fields.Char(
        string="Name",
        required=True,translate=True
    )
    phone = fields.Char(
        string="Phone Number",
        required=True,translate=True
    )
    email = fields.Char(
        string="E-mail",
        required=True
    )
    area = fields.Char(
        string="Area",
        required=True,translate=True
    )
    brand = fields.Char(
        string="Brand",
        required=True,translate=True
    )
    model = fields.Char(
        string="Model",
        required=True,translate=True
    )
    year = fields.Char(
        string="Year",
        required = True,translate=True
    )
    payment = fields.Char(
        string="Payment",
        required=True,translate=True
    )
    payment_method = fields.Char(string="Payment Method",translate=True)
    working_status = fields.Char(string="Working Status",translate=True)
    home_address = fields.Char(string="Home Address",translate=True)
    work_address = fields.Char(string="Work Address",translate=True)
    job_title = fields.Char(string="Job Title",translate=True)
    deposit_available = fields.Char(string="Deposit Available",translate=True)
    no_commercial_register_tax_card = fields.Char(string="No Commercial Register Or Tax Card",translate=True)
    qualification = fields.Char(string="Qualification",translate=True)
    id_card_front = fields.Image(string="ID Card Front")
    id_card_back = fields.Image(string="ID Card Back")
    tax_card_front = fields.Image(string="Tax Card Front")
    tax_card_back = fields.Image(string="Tax Card Back")





