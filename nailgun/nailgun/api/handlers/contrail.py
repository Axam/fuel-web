# -*- coding: utf-8 -*-

#    Copyright 2013 Mirantis, Inc.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

"""
Handlers dealing with clusters
"""

import web

from nailgun.api.handlers.base import BaseHandler
from nailgun.api.handlers.base import content_json
from nailgun.api.validators.cluster import AttributesValidator
from nailgun.db import db
from nailgun.db.sqlalchemy.models import Cluster
from nailgun.db.sqlalchemy.models import ContrailAttributes
from nailgun.logger import logger


class ContrailAttributesHandler(BaseHandler):
    """Cluster contrail attributes handler
    """

    fields = (
        "editable",
    )

    validator = AttributesValidator

    @content_json
    def GET(self, cluster_id):
        """:returns: JSONized Cluster attributes.
        :http: * 200 (OK)
               * 404 (cluster not found in db)
               * 500 (cluster has no contrail attributes)
        """
        contrail = self.get_object_or_404(ContrailAttributes, cluster_id)

        return {
            "editable": contrail.editable
        }

    @content_json
    def PUT(self, cluster_id):
        """:returns: JSONized Cluster attributes.
        :http: * 200 (OK)
               * 400 (wrong attributes data specified)
               * 404 (cluster not found in db)
               * 500 (cluster has no attributes)
        """
        cluster = self.get_object_or_404(Cluster, cluster_id)
        if not cluster.attributes:
            raise web.internalerror("No attributes found!")

        data = self.checked_data()

        if cluster.are_attributes_locked:
            error = web.forbidden()
            error.data = "Environment attributes can't be changed " \
                         "after, or in deploy."
            raise error

        for key, value in data.iteritems():
            setattr(cluster.contrail, key, value)
        cluster.add_pending_changes("contrail_attributes")

        db().commit()
        return {"editable": cluster.contrail.editable}


class ContrailAttributesDefaultsHandler(BaseHandler):
    """Cluster default attributes handler
    """

    fields = (
        "editable",
    )

    @content_json
    def GET(self, cluster_id):
        """:returns: JSONized default Cluster attributes.
        :http: * 200 (OK)
               * 404 (cluster not found in db)
               * 500 (cluster has no attributes)
        """
        attrs = {'as_number' : 64512,
                 'wan_gateways' : []
                }
        return {"editable": attrs}