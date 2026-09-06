# -*- coding: utf-8 -*-
import re

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class CourseCourse(models.Model):
    _name = 'course.course'
    _description = 'Course'
    _order = 'title'

    category_id = fields.Many2one('course.category', string='Category', required=True)
    subcategory_id = fields.Many2one('course.subcategory', string='Subcategory',
                                      domain="[('category_id', '=', category_id)]")
    title = fields.Char(string='Title', required=True)
    slug = fields.Char(string='Slug', copy=False)
    image = fields.Image(string='Image')

    price = fields.Monetary(string='Price')
    discount = fields.Float(string='Discount (%)')
    price_after_discount = fields.Monetary(
        string='Price After Discount', compute='_compute_price_after_discount', store=True
    )  # [Claude addition]
    currency_id = fields.Many2one(
        'res.currency', string='Currency',
        default=lambda self: self.env.company.currency_id
    )

    duration = fields.Float(string='Duration (Hours)')

    level = fields.Selection([
        ('beginner', 'Beginner'),
        ('intermediate', 'Intermediate'),
        ('advanced', 'Advanced'),
    ], string='Level', required=True, default='beginner')

    description = fields.Html(string='Description')

    featured = fields.Selection([
        ('yes', 'Yes'),
        ('no', 'No'),
    ], string='Featured', default='no')

    active = fields.Boolean(default=True)  # [Claude addition]

    # [Claude addition] smart button support
    lesson_ids = fields.One2many('course.lesson', 'course_id', string='Lessons')
    lesson_count = fields.Integer(string='Lessons', compute='_compute_lesson_count')

    _sql_constraints = [
        # [Claude addition] slug must be unique since it identifies the course (e.g. in a URL)
        ('slug_uniq', 'unique(slug)', 'This Slug is already used by another Course.'),
    ]

    def _compute_lesson_count(self):
        for course in self:
            course.lesson_count = len(course.lesson_ids)

    def action_view_lessons(self):
        self.ensure_one()
        return {
            'name': 'Lessons',
            'type': 'ir.actions.act_window',
            'res_model': 'course.lesson',
            'view_mode': 'list,form',
            'domain': [('course_id', '=', self.id)],
            'context': {'default_course_id': self.id},
        }

    @api.depends('price', 'discount')
    def _compute_price_after_discount(self):
        for course in self:
            if course.price and course.discount:
                course.price_after_discount = course.price * (1 - (course.discount / 100.0))
            else:
                course.price_after_discount = course.price

    @api.constrains('discount')
    def _check_discount(self):
        for course in self:
            if course.discount and not (0 <= course.discount <= 100):
                raise ValidationError(_('Discount must be between 0 and 100.'))

    @api.onchange('title')
    def _onchange_title(self):
        # [Claude addition] auto-generate a URL-friendly slug from the title
        if self.title and not self.slug:
            slug = self.title.strip().lower()
            slug = re.sub(r'[^a-z0-9]+', '-', slug).strip('-')
            self.slug = slug

    @api.onchange('category_id')
    def _onchange_category_id(self):
        # [Claude addition] clear subcategory if it no longer matches the selected category
        if self.subcategory_id and self.subcategory_id.category_id != self.category_id:
            self.subcategory_id = False
