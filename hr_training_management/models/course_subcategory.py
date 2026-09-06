# -*- coding: utf-8 -*-
from odoo import fields, models


class CourseSubcategory(models.Model):
    _name = 'course.subcategory'
    _description = 'Course Subcategory'
    _order = 'name'

    category_id = fields.Many2one('course.category', string='Category',
                                   required=True, ondelete='cascade')
    name = fields.Char(string='Name', required=True, translate=True)
    image = fields.Image(string='Image')
    description = fields.Html(string='Description')
    active = fields.Boolean(default=True)  # [Claude addition]

    _sql_constraints = [
        # [Claude addition] avoid duplicate subcategory names within the same category
        ('category_name_uniq', 'unique(category_id, name)',
         'This Subcategory name already exists under the selected Category.'),
    ]
