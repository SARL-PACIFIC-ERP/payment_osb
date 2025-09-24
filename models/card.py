# coding: utf-8
#
# Copyright © Lyra Network.
# This file is part of OSB plugin for Odoo. See COPYING.md for license details.
#
# Author:    Lyra Network (https://www.lyra.com)
# Copyright: Copyright © Lyra Network
# License:   http://www.gnu.org/licenses/agpl.html GNU Affero General Public License (AGPL v3)

from odoo import models, fields
from ..helpers import constants

class OsbCard(models.Model):
    _name = 'osb.card'
    _description = 'OSB payment card'
    _rec_name = 'label'
    _order = 'label'

    code = fields.Char()
    label = fields.Char()

    def init(self):
        cards = constants.OSB_CARDS

        for c, l in cards.items():
            card = self.search([('code', '=', c)])

            if not card:
                self.create({'code': c, 'label': l})
