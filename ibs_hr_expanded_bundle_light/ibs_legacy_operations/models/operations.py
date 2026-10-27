from odoo import api, fields, models, _
from odoo.exceptions import ValidationError, UserError

STAGES = [("draft","Draft"),("submitted","Submitted"),("approved","Approved"),("rejected","Rejected"),("done","Done")]

class IbsHrWarehouse(models.Model):
    _name = "ibs.hr.warehouse"
    _description = "Warehouse"
    _inherit = ['mail.thread', 'mail.activity.mixin']
    name = fields.Char(required=True, tracking=True)
    company_id = fields.Many2one("res.company", default=lambda self: self.env.company, required=True, index=True)
    location = fields.Char()
    manager_id = fields.Many2one("hr.employee")
    notes = fields.Text()

class IbsHrInventoryCategory(models.Model):
    _name = "ibs.hr.inventory.category"
    _description = "Inventory Category"
    _inherit = ['mail.thread', 'mail.activity.mixin']
    name = fields.Char(required=True, tracking=True)
    company_id = fields.Many2one("res.company", default=lambda self: self.env.company, required=True, index=True)
    description = fields.Text()

class IbsHrInventoryProduct(models.Model):
    _name = "ibs.hr.inventory.product"
    _description = "Inventory Product"
    _inherit = ['mail.thread', 'mail.activity.mixin']
    name = fields.Char(required=True, tracking=True)
    company_id = fields.Many2one("res.company", default=lambda self: self.env.company, required=True, index=True)
    sku = fields.Char()
    category_id = fields.Many2one("ibs.hr.inventory.category", ondelete="restrict", index=True)
    warehouse_id = fields.Many2one("ibs.hr.warehouse", ondelete="restrict", index=True)
    unit_cost = fields.Float()
    quantity_on_hand = fields.Float()
    reorder_level = fields.Float()
    description = fields.Text()

class IbsHrStockMovement(models.Model):
    _name = "ibs.hr.stock.movement"
    _description = "Stock Movement"
    _inherit = ['mail.thread', 'mail.activity.mixin']
    name = fields.Char(required=True, tracking=True)
    company_id = fields.Many2one("res.company", default=lambda self: self.env.company, required=True, index=True)
    product_id = fields.Many2one("ibs.hr.inventory.product", ondelete="restrict", index=True)
    movement_type = fields.Selection([('in', 'In'), ('out', 'Out'), ('adjustment', 'Adjustment')])
    quantity = fields.Float()
    date = fields.Datetime()
    employee_id = fields.Many2one("hr.employee")
    reference = fields.Char()
    notes = fields.Text()
    @api.constrains("quantity")
    def _check_quantity(self):
        for rec in self:
            if rec.quantity <= 0: raise ValidationError(_("Movement quantity must be positive."))

class IbsHrPurchaseRequest(models.Model):
    _name = "ibs.hr.purchase.request"
    _description = "Purchase Request"
    _inherit = ['mail.thread', 'mail.activity.mixin']
    name = fields.Char(required=True, tracking=True)
    company_id = fields.Many2one("res.company", default=lambda self: self.env.company, required=True, index=True)
    requester_id = fields.Many2one("hr.employee")
    department_id = fields.Many2one("hr.department")
    request_date = fields.Date()
    needed_date = fields.Date()
    state = fields.Selection(STAGES, default="draft", required=True, tracking=True)
    approver_id = fields.Many2one("hr.employee")
    approved_date = fields.Datetime()
    reason = fields.Text()
    line_ids = fields.One2many("ibs.hr.purchase.line", "request_id")
    def action_submit(self):
        for rec in self:
            if rec.state != "draft": raise UserError(_("Only draft records can be submitted."))
            rec.state = "submitted"
    def action_approve(self):
        for rec in self:
            if rec.state != "submitted": raise UserError(_("Only submitted records can be approved."))
            rec.state = "approved"
    def action_reject(self):
        for rec in self:
            if rec.state != "submitted": raise UserError(_("Only submitted records can be rejected."))
            rec.state = "rejected"

class IbsHrPurchaseLine(models.Model):
    _name = "ibs.hr.purchase.line"
    _description = "Purchase Request Line"
    _inherit = ['mail.thread', 'mail.activity.mixin']
    name = fields.Char(required=True, tracking=True)
    company_id = fields.Many2one("res.company", default=lambda self: self.env.company, required=True, index=True)
    request_id = fields.Many2one("ibs.hr.purchase.request", ondelete="restrict", index=True)
    product_id = fields.Many2one("ibs.hr.inventory.product", ondelete="restrict", index=True)
    quantity = fields.Float()
    estimated_unit_cost = fields.Float()
    notes = fields.Text()

class IbsHrInvestigation(models.Model):
    _name = "ibs.hr.investigation"
    _description = "Employee Investigation"
    _inherit = ['mail.thread', 'mail.activity.mixin']
    name = fields.Char(required=True, tracking=True)
    company_id = fields.Many2one("res.company", default=lambda self: self.env.company, required=True, index=True)
    employee_id = fields.Many2one("hr.employee")
    incident_date = fields.Date()
    investigator_id = fields.Many2one("hr.employee")
    state = fields.Selection(STAGES, default="draft", required=True, tracking=True)
    description = fields.Text()
    findings = fields.Text()
    resolution = fields.Text()
    def action_submit(self):
        for rec in self:
            if rec.state != "draft": raise UserError(_("Only draft records can be submitted."))
            rec.state = "submitted"
    def action_approve(self):
        for rec in self:
            if rec.state != "submitted": raise UserError(_("Only submitted records can be approved."))
            rec.state = "approved"
    def action_reject(self):
        for rec in self:
            if rec.state != "submitted": raise UserError(_("Only submitted records can be rejected."))
            rec.state = "rejected"

class IbsHrClearance(models.Model):
    _name = "ibs.hr.clearance"
    _description = "Employee Clearance"
    _inherit = ['mail.thread', 'mail.activity.mixin']
    name = fields.Char(required=True, tracking=True)
    company_id = fields.Many2one("res.company", default=lambda self: self.env.company, required=True, index=True)
    employee_id = fields.Many2one("hr.employee")
    last_working_date = fields.Date()
    approver_id = fields.Many2one("hr.employee")
    state = fields.Selection(STAGES, default="draft", required=True, tracking=True)
    notes = fields.Text()
    item_ids = fields.One2many("ibs.hr.clearance.item", "clearance_id")
    def action_submit(self):
        for rec in self:
            if rec.state != "draft": raise UserError(_("Only draft records can be submitted."))
            rec.state = "submitted"
    def action_approve(self):
        for rec in self:
            if rec.state != "submitted": raise UserError(_("Only submitted records can be approved."))
            rec.state = "approved"
    def action_reject(self):
        for rec in self:
            if rec.state != "submitted": raise UserError(_("Only submitted records can be rejected."))
            rec.state = "rejected"

class IbsHrClearanceItem(models.Model):
    _name = "ibs.hr.clearance.item"
    _description = "Clearance Item"
    _inherit = ['mail.thread', 'mail.activity.mixin']
    name = fields.Char(required=True, tracking=True)
    company_id = fields.Many2one("res.company", default=lambda self: self.env.company, required=True, index=True)
    clearance_id = fields.Many2one("ibs.hr.clearance", ondelete="restrict", index=True)
    department_id = fields.Many2one("hr.department")
    owner_id = fields.Many2one("hr.employee")
    complete = fields.Boolean()
    notes = fields.Text()

class IbsHrNotice(models.Model):
    _name = "ibs.hr.notice"
    _description = "Employee Notice"
    _inherit = ['mail.thread', 'mail.activity.mixin']
    name = fields.Char(required=True, tracking=True)
    company_id = fields.Many2one("res.company", default=lambda self: self.env.company, required=True, index=True)
    body = fields.Html()
    publish_date = fields.Date()
    expiry_date = fields.Date()
    department_id = fields.Many2one("hr.department")
    employee_ids = fields.Many2many("hr.employee", relation="ibs_hr_notice_employee_ids_rel")
    state = fields.Selection(STAGES, default="draft", required=True, tracking=True)
    def action_submit(self):
        for rec in self:
            if rec.state != "draft": raise UserError(_("Only draft records can be submitted."))
            rec.state = "submitted"
    def action_approve(self):
        for rec in self:
            if rec.state != "submitted": raise UserError(_("Only submitted records can be approved."))
            rec.state = "approved"
    def action_reject(self):
        for rec in self:
            if rec.state != "submitted": raise UserError(_("Only submitted records can be rejected."))
            rec.state = "rejected"

class IbsHrTeamMeeting(models.Model):
    _name = "ibs.hr.team.meeting"
    _description = "Team Meeting"
    _inherit = ['mail.thread', 'mail.activity.mixin']
    name = fields.Char(required=True, tracking=True)
    company_id = fields.Many2one("res.company", default=lambda self: self.env.company, required=True, index=True)
    start_at = fields.Datetime()
    end_at = fields.Datetime()
    organizer_id = fields.Many2one("hr.employee")
    employee_ids = fields.Many2many("hr.employee", relation="ibs_hr_team_meeting_employee_ids_rel")
    location = fields.Char()
    agenda = fields.Html()
    minutes = fields.Html()
    state = fields.Selection(STAGES, default="draft", required=True, tracking=True)
    def action_submit(self):
        for rec in self:
            if rec.state != "draft": raise UserError(_("Only draft records can be submitted."))
            rec.state = "submitted"
    def action_approve(self):
        for rec in self:
            if rec.state != "submitted": raise UserError(_("Only submitted records can be approved."))
            rec.state = "approved"
    def action_reject(self):
        for rec in self:
            if rec.state != "submitted": raise UserError(_("Only submitted records can be rejected."))
            rec.state = "rejected"
    @api.constrains("start_at", "end_at")
    def _check_dates(self):
        for rec in self:
            if rec.start_at and rec.end_at and rec.end_at < rec.start_at: raise ValidationError(_("Meeting end must follow start."))

class IbsHrEmployeeAsset(models.Model):
    _name = "ibs.hr.employee.asset"
    _description = "Employee Asset Assignment"
    _inherit = ['mail.thread', 'mail.activity.mixin']
    name = fields.Char(required=True, tracking=True)
    company_id = fields.Many2one("res.company", default=lambda self: self.env.company, required=True, index=True)
    employee_id = fields.Many2one("hr.employee")
    product_id = fields.Many2one("ibs.hr.inventory.product", ondelete="restrict", index=True)
    assigned_date = fields.Date()
    returned_date = fields.Date()
    condition = fields.Char()
    notes = fields.Text()
