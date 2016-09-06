# Copyright 2015 Cisco Systems Inc.
# All Rights Reserved.
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

from rally.benchmark import context
from rally.common import utils
from rally.common import log as logging
from rally import consts
from rally import osclients
from rally import db
import sys
import pdb

LOG = logging.getLogger(__name__)


@context.context(name="server_groups", order=2020)
class ServerGroupsGenerator(context.Context):
    """Create a server group."""

    CONFIG_SCHEMA = {
        "type": "array",
        "$schema": consts.JSON_SCHEMA,
        "items": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                },
                "policies": {
                    "type": "array",
                    "items": {
                        "type": "string"
                    },
                },
            },
            "additionalProperties": False,
            "required": ["name", "policies"],
        }
    }

    POLICY = (
        'affinity',
        'anti-affinity',
    )

    def __init__(self, ctx):
        """Create one nova client to be used through out this test.
        Instance Variables:
            nova        nova client
            uuid        rally task UUID
        """
        super(ServerGroupsGenerator, self).__init__(ctx)
        self.groups = []
        task = db.task_get_detailed_last()
        self.uuid = task['uuid']
        self.nova = osclients.Clients(self.context["admin"]["endpoint"]).nova()
        LOG.info("%s:%s() task: %s, config: %s",
                 self.__class__.__name__, sys._getframe().f_code.co_name, self.uuid, self.config)

    def setup(self):
        """This method is called before the task start."""
        self._create_server_groups()

    def cleanup(self):
        """This method is called after the task finish."""
        self._delete_server_groups()
        self._report()

    def _create_server_groups(self):
        """create server groups
        Keys in server_groups object:
            ['_info', '_loaded', 'id', 'manager', 'members', 'metadata', 'name', 'policies']
        Keys in manager object:
            ['api']
        """
        try:
            for d in self.config:
                for p in d['policies']:
                    if p not in ServerGroupsGenerator.POLICY:
                        break
                    group = self.nova.server_groups.create(**d)
                    self.groups.append(group)
                    uuid = getattr(group, 'id', '')
                    name = getattr(group, 'name', '')
                    LOG.info("%s:%s() name: %s, uuid: %s",
                             self.__class__.__name__, sys._getframe().f_code.co_name, name, uuid)
        except Exception as e:
            LOG.exception(e)
            raise

    def _delete_server_groups(self):
        try:
            for group in self.groups:
                uuid = getattr(group, 'id', '')
                name = getattr(group, 'name', '')
                self.nova.server_groups.delete(uuid)
                LOG.info("%s:%s() name: %s, uuid: %s",
                         self.__class__.__name__, sys._getframe().f_code.co_name, name, uuid)
        except Exception as e:
            LOG.exception(e)
            raise

    def _report(self):
        """Information dump to STDOUT after testing.
        """
        pass
