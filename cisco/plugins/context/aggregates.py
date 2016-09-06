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
import json
import pdb

sys.path.append('/opt/rally/plugins/cisco/common')
import report

LOG = logging.getLogger(__name__)


@context.context(name="aggregates", order=2010)
class AggregatesGenerator(context.Context):
    """Create host aggregates.
        TODO support multiple aggregates.

    Configurable parameters that can be overwritten by that defined in JSON or YAML files.
    name        name of host aggregate
                if not configured, it is randomly generated
    zone_name   availability zone name
                if not configured, use zone with the most nova-compute hosts
    match_host  sub-string of a nova-compute hostname
    metadata    if not configured, do not use
    """

    CONFIG_SCHEMA = {
        "type": "object",
        "$schema": consts.JSON_SCHEMA,
        "additionalProperties": False,
        "properties": {
            "name": {
                "type": "string",
            },
            "zone_name": {
                "type": "string",
            },
            "match_host": {
                "type": "array",
                "items": {
                    "type": "string",
                },
            },
            "metadata": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": {
                        "type": "string",
                    },
                },
            },
        }
    }

    """Selected fields from service object.
    List of keys in service object:
        [ '_info', '_loaded', 'binary', 'disabled_reason', 'host', 'id',
        'manager', 'state', 'status', 'updated_at', 'zone' ]
    """
    FIELDS = ['binary', 'host', 'id', 'state', 'status', 'zone']

    def __init__(self, ctx):
        """Create one nova client to be used through out this test.
            Get the list of availability zones.
            Find the availablity zone to be used for this test.
        Instance Variables:
            ag          host aggregate
            ag_name     save away to print reports and debug logs
            config      base class set to this to DEFAULT_CONFIG
                        overwritten by configuration from JSON or YAML
            hosts       list of nova-compute hostname
            nova        nova client
            uuid        rally task UUID
            zones       list of availability zones
            zone_name   selected name of availablility zone if one is not configured
        """
        super(AggregatesGenerator, self).__init__(ctx)
        self.ag = None
        self.ag_name = None
        self.hosts = None
        self.zone_name = None
        task = db.task_get_detailed_last()
        self.uuid = task['uuid']
        self.nova = osclients.Clients(self.context["admin"]["endpoint"]).nova()
        self.zones = self._get_zones()
        if 'name' not in self.config:
            self.config['name'] = utils.generate_random_name(prefix="rally_ag_")
        if 'zone_name' not in self.config:
            self.config['zone_name'] = self.zone_name
        LOG.info("%s:%s() task: %s, config: %s",
                 self.__class__.__name__, sys._getframe().f_code.co_name, self.uuid, self.config)

    def setup(self):
        """This method is called before the task start."""
        self.hosts = self._get_hosts()
        self.ag_name, self.ag = self._create_aggregate()

    def cleanup(self):
        """This method is called after the task finish."""
        self._delete_aggregate(self.ag_name, self.ag)
        self._report()

    def _get_zones(self):
        """Get the list of all availability zones.
            Pick availability zone with the most up and enabled nova-compute hosts.
        List of keys in zone object:
            [ '_info', '_loaded', 'binary', 'disabled_reason', 'host', 'id',
            'manager', 'state', 'status', 'updated_at', 'zone' ]
        :returns zones: list of all availability zones
        """
        zones = {}
        self.zone_name = None
        try:
            largest = 0
            objs = self.nova.services.list()
            for o in objs:
                d = {}
                for field in AggregatesGenerator.FIELDS:
                    d[field] = getattr(o, field, '')
                LOG.debug("%s:%s() service: %s", self.__class__.__name__, sys._getframe().f_code.co_name, d)
                if d['binary'] == 'nova-compute' and d['state'] == 'up' and d['status'] == 'enabled':
                    if d['zone'] not in zones:
                        zones[d['zone']] = []
                    if d['host'] not in zones[d['zone']]:
                        zones[d['zone']].append(d['host'])
            LOG.debug("%s:%s() %s", self.__class__.__name__, sys._getframe().f_code.co_name, zones)
            for zone in zones:
                if len(zones[zone]) >= largest:
                    largest = len(zones[zone])
                    self.zone_name = zone
            LOG.debug("%s:%s() selected: %s", self.__class__.__name__, sys._getframe().f_code.co_name, self.zone_name)
        except Exception as e:
            LOG.exception(e)
            raise
        finally:
            return zones

    def _get_hosts(self):
        """Get the list of nova-compute hosts to be added to a host aggregate.
            Go through the service list
                Look at all the up and enabled nova-compute hosts
            If configured 'match_host' in YAML or JSON
                and this host matches
                then, add this host to the list
            Otherwise, check if this host is in the selected zone
                then, add this host to the list
        :returns hosts: a list of nova-compute hostname
        """
        hosts = []
        try:
            objs = self.nova.services.list()
            for o in objs:
                d = {}
                for field in AggregatesGenerator.FIELDS:
                    d[field] = getattr(o, field, '')
                LOG.debug("%s:%s() service: %s", self.__class__.__name__, sys._getframe().f_code.co_name, d)
                if d['binary'] == 'nova-compute' and d['state'] == 'up' and d['status'] == 'enabled':
                    host = d['host']
                    if 'match_host' in self.config:
                        for match in self.config['match_host']:
                            if match in host:
                                hosts.append(host)
                                break
                    elif host in self.zones[self.config['zone_name']]:
                        hosts.append(host)
        except Exception as e:
            LOG.exception(e)
            raise
        finally:
            LOG.debug("%s:%s() %s", self.__class__.__name__, sys._getframe().f_code.co_name, hosts)
            return hosts

    def _create_aggregate(self):
        """Create a host aggregate.
        List of keys in aggregate object:
            ['_info', '_loaded', 'availability_zone', 'created_at', 'deleted',
            'deleted_at', 'id', 'manager', 'name', 'updated_at']
        Schema only allows variable list,
            but openstack nova uses a variable dictionary for metadata
        self.config['metadata'] is a list, and set_metadata() expects a dictionary
            hence call set_metadata() multiple times
        :returns ag_name:   host aggregate name
        :returns ag:        host aggregate object
        """
        ag = None
        ag_name = ""
        try:
            ag = self.nova.aggregates.create(self.config['name'], self.config['zone_name'])
            for host in self.hosts:
                ag.add_host(host)
            if 'metadata' in self.config:
                for meta in self.config['metadata']:
                    ag.set_metadata(meta)
            ag_name = ag.name
            LOG.debug("%s:%s() %s", self.__class__.__name__, sys._getframe().f_code.co_name, ag_name)
        except Exception as e:
            LOG.exception(e)
            raise
        finally:
            return (ag_name, ag)

    def _delete_aggregate(self, ag_name, ag):
        """Delete a host aggregate.
        :param ag_name: host aggregate name
        :param ag:      host aggregate object
        """
        try:
            for host in self.hosts:
                ag.remove_host(host)
            ag.delete()
            LOG.debug("%s:%s() %s", self.__class__.__name__, sys._getframe().f_code.co_name, ag_name)
        except Exception as e:
            LOG.exception(e)
            raise

    def _report(self):
        """Information dump to STDOUT after testing.
        """
        data_file = report.get_aggregate_file(self.uuid)
        d = {}
        d['name'] = self.ag_name
        d['zone'] = self.config['zone_name']
        d['hosts'] = self.hosts
        d['metadata'] = self.config['metadata']
        with open(data_file, 'a') as f:
            f.write(json.dumps(d))
            f.write("\n")
        print "\n%s:%s(): Aggregate used written to:\n\t%s" % (
            self.__class__.__name__, sys._getframe().f_code.co_name, data_file)
