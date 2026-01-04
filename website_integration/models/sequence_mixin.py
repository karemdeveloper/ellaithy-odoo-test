from odoo import api, fields, models


class SequenceMixin(models.AbstractModel):
    _name = "sequence.mixin"
    _description = "Sequence Mixin"

    name = fields.Char(string="Reference", default="New", readonly=True, copy=False)

    _sequence_code = None

    @api.model
    def create(self, vals):
        if vals.get("name", "New") == "New" and self._sequence_code:
            vals["name"] = (
                self.env["ir.sequence"].next_by_code(self._sequence_code) or "New"
            )
        return super().create(vals)
