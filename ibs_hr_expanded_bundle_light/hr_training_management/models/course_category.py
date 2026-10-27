# -*- coding: utf-8 -*-
from odoo import fields, models


class CourseCategory(models.Model):
    _name = 'course.category'
    _description = 'Course Category'
    _order = 'name'

    name = fields.Char(string='Name', required=True, translate=True)
    image = fields.Image(string='Image')
    description = fields.Html(string='Description')
    active = fields.Boolean(default=True)  # [Claude addition]

    # [Claude addition] smart button support
    subcategory_ids = fields.One2many('course.subcategory', 'category_id', string='Subcategories')
    subcategory_count = fields.Integer(string='Subcategories', compute='_compute_subcategory_count')

    _sql_constraints = [
        # [Claude addition] avoid duplicate category names
        ('name_uniq', 'unique(name)', 'Course Category name must be unique.'),
    ]

    def _compute_subcategory_count(self):
        for category in self:
            category.subcategory_count = len(category.subcategory_ids)

    def action_view_subcategories(self):
        self.ensure_one()
        return {
            'name': 'Subcategories',
            'type': 'ir.actions.act_window',
            'res_model': 'course.subcategory',
            'view_mode': 'list,form',
            'domain': [('category_id', '=', self.id)],
            'context': {'default_category_id': self.id},
        }
