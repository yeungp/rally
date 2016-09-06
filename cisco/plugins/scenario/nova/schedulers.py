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

import jsonschema

from rally.benchmark.scenarios import base
from rally.benchmark import types as types
from rally.benchmark import validation
from rally.common import log as logging
from rally import consts
from rally import db
from rally import objects
from rally import osclients
from rally import exceptions as rally_exceptions
from rally.plugins.openstack.scenarios.cinder import utils as cinder_utils
from rally.plugins.openstack.scenarios.nova import utils
from rally.plugins.openstack.wrappers import network as network_wrapper

import sys
import json
import pdb
sys.path.append('/opt/rally/plugins/cisco/common')
import report
import lock

LOG = logging.getLogger(__name__)


class NovaScheduler(utils.NovaScenario,
                    cinder_utils.CinderScenario):

    RESOURCE_NAME_PREFIX = "rally_scheduler_"
    RESOURCE_NAME_LENGTH = 15

    """Optional additional arguments for server creation.
    """
    OPTIONS = (
        "hint",
        "group",
    )
    SAME = (
        "same_host",
        "soft_same_host",
        "same_rack",
    )
    DIFFERENT = (
        "different_host",
        "soft_different_host",
        "different_rack",
    )

    """List of boot servers"""
    vms = []

    @types.set(image=types.ImageResourceType,
               flavor=types.FlavorResourceType)
    @validation.image_valid_on_flavor("flavor", "image")
    @validation.required_services(consts.Service.NOVA)
    @validation.required_openstack(users=True)
    @base.scenario(context={"cleanup": ["nova"]})
    def boot_server(self, image, flavor, auto_assign_nic=False, **kwargs):
        """Boot a server.
        Assumes that cleanup is done elsewhere.
        :param image: image to be used to boot an instance
        :param flavor: flavor to be used to boot an instance
        :param auto_assign_nic: True if NICs should be assigned
        :param kwargs: Optional additional arguments for server creation

        Keys in server object:
            ['OS-DCF:diskConfig', 'OS-EXT-AZ:availability_zone', 'OS-EXT-STS:power_state',
            'OS-EXT-STS:task_state', 'OS-EXT-STS:vm_state', 'OS-SRV-USG:launched_at',
            'OS-SRV-USG:terminated_at', '_info', '_loaded', 'accessIPv4', 'accessIPv6',
            'addresses', 'config_drive', 'created', 'flavor', 'hostId', 'id', 'image',
            'key_name', 'links', 'manager', 'metadata', 'name',
            'os-extended-volumes:volumes_attached', 'progress', 'status', 'tenant_id',
            'updated', 'user_id' ]
        Keys in server_admin object:
            ['OS-DCF:diskConfig', 'OS-EXT-AZ:availability_zone', 'OS-EXT-SRV-ATTR:host',
            'OS-EXT-SRV-ATTR:hypervisor_hostname', 'OS-EXT-SRV-ATTR:instance_name',
            'OS-EXT-STS:power_state', 'OS-EXT-STS:task_state', 'OS-EXT-STS:vm_state',
            'OS-SRV-USG:launched_at', 'OS-SRV-USG:terminated_at', '_info', '_loaded',
            'accessIPv4', 'accessIPv6', 'addresses', 'config_drive', 'created', 'flavor',
            'hostId', 'id', 'image', 'key_name', 'links', 'manager', 'metadata', 'name',
            'os-extended-volumes:volumes_attached', 'progress', 'status', 'tenant_id',
            'updated', 'user_id']
        """
        empty_kwargs = {}
        deploys = db.deployment_list()
        admin = deploys[0].admin
        nova = osclients.Clients(objects.Endpoint(**admin)).nova()
        hints = self._get_hints(nova, **kwargs)
        task = db.task_get_detailed_last()
        data_file = report.get_boot_status_file(task['uuid'])
        d = {}
        try:
            server = self._boot_server(image,
                                       flavor,
                                       scheduler_hints=hints,
                                       auto_assign_nic=auto_assign_nic,
                                       **empty_kwargs)
            d['id'] = getattr(server, 'id')
            server_admin = nova.servers.get(d['id'])
            d['name'] = getattr(server_admin, 'name')
            d['zone'] = getattr(server_admin, 'OS-EXT-AZ:availability_zone')
            d['state'] = getattr(server_admin, 'OS-EXT-STS:vm_state')
            d['host'] = getattr(server_admin, "OS-EXT-SRV-ATTR:host", '')
            attr = getattr(server_admin, 'flavor')
            d['flavor'] = attr['id']
        except Exception as e:
            LOG.exception(e)
            d['name'] = 'unknown'
            d['state'] = 'error'
        finally:
            with open(data_file, 'a') as f:
                f.write(json.dumps(d))
                f.write("\n")
            LOG.info("%s:%s() %s", self.__class__.__name__, sys._getframe().f_code.co_name, d)
            NovaScheduler.vms.append(d)

    def _get_hints(self, nova, **kwargs):    
        """Construct arguments if configured with options.
        :param nova: nova client
        :param kwargs: args from JSON or YAML file
        """
        key = None
        hints = None
        if 'hint' in kwargs:
            key = kwargs['hint']
            if key in NovaScheduler.SAME:
                hints = self._get_one_server(key)
            elif key in NovaScheduler.DIFFERENT:
                hints = self._get_all_servers(key)
        elif 'group' in kwargs:
            name = kwargs['group']
            hints = self._get_group_uuid(nova, name)
        LOG.info("%s:%s() %s", self.__class__.__name__, sys._getframe().f_code.co_name, hints)
        if hints is None or len(hints) == 0:
            return None
        else:
            return hints

    def _get_one_server(self, key):
        """Get the first active instance.
        :param key: hint key of nova scheduler
        """
        hints = {}
        for vm in NovaScheduler.vms:
            if vm['state'] == 'active':
                hints[key] = vm['id']
                break
        LOG.info("%s:%s() %s: %s", self.__class__.__name__,
                  sys._getframe().f_code.co_name, key, hints)
        return hints

    def _get_all_servers(self, key):
        """Get a list of all active instances.
        :param key: hint key of nova scheduler
        """
        hints = {}
        hosts = []
        for vm in NovaScheduler.vms:
            if vm['state'] == 'active':
                hosts.append(vm['id'])
        if len(hosts) > 0:
            hints[key] = hosts
        LOG.info("%s:%s() %s: %s", self.__class__.__name__,
                  sys._getframe().f_code.co_name, key, hints)
        return hints

    def _get_group_uuid(self, nova, name):
        """From group name, get group UUID
        :param nova: nova client
        :param name: server group name
        """
        hints = {}
        try:
            groups = nova.server_groups.list()
            for group in groups:
                gname = getattr(group, 'name', '')
                if name == gname:
                    hints['group'] = getattr(group, 'id', '')
        except Exception as e:
            LOG.exception(e)
        finally:
            LOG.info("%s:%s() %s: %s", self.__class__.__name__,
                     sys._getframe().f_code.co_name, name, hints)
            return hints
