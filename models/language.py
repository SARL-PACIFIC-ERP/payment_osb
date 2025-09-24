# coding: utf-8
#
# Copyright © Lyra Network.
# This file is part of OSB plugin for Odoo. See COPYING.md for license details.
#
# Author:    Lyra Network (https://www.lyra.com)
# Copyright: Copyright © Lyra Network
# License:   http://www.gnu.org/licenses/agpl.html GNU Affero General Public License (AGPL v3)

from odoo import models, fields
from ..helpers import constants, tools

class OsbLanguage(models.Model):
    _name = 'osb.language'
    _description = 'OSB language'
    _rec_name = 'label'
    _order = 'label'

    code = fields.Char()
    label = fields.Char()

    def init(self):
        languages = constants.OSB_LANGUAGES

        for c, l in languages.items():
            lang = self.search([('code', '=', c)])

            if not lang:
                self.create({'code': c, 'label': l})
