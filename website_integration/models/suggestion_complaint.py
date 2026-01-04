from odoo import models, fields, api

class SuggestionComplaint(models.Model):
    _name = 'suggestion.complaint'
    _description = 'Suggestions and Complaints'
    _inherit = 'sequence.mixin'
    _sequence_code = 'suggestion.complaint'
    first_name = fields.Char(string="First Name", required=True,translate=True)
    last_name = fields.Char(string="Last Name", required=True,translate=True)

    phone = fields.Char(string="Phone", required=True,translate=True)
    email = fields.Char(string="Email")

    suggestion_complaint = fields.Text(
        string="Suggestion / Complaint",
        required=True
    )

