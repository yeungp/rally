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

from rally.benchmark import sla
from rally.common.i18n import _
from rally.common.plugin import plugin
from rally.common import log as logging
from rally import consts
from rally import db
from rally import objects
from rally import osclients
import sys
import pandas as pd
import pdb

sys.path.append('/opt/rally/plugins/cisco/common')
import report

LOG = logging.getLogger(__name__)


@plugin.configure(name="hypervisors_usage")
class HypervisorUsage(sla.SLA):
    """Hardware resource usage in all hypervisors.
        Measure the even usage of vCPU, RAM, and disk usage in all hypervisors.
    """
    CONFIG_SCHEMA = {
        "type": "object",
        "$schema": consts.JSON_SCHEMA,
        "properties": {
            "std_free_vcpus": {
                "type": "number",
                "minimum": 0.0,
            },
            "std_free_ram": {
                "type": "number",
                "minimum": 0.0,
            },
            "std_free_disk": {
                "type": "number",
                "minimum": 0.0,
            },
            "match_host": {
                "type": "array",
                "items": {
                    "type": "string",
                },
            },
        }
    }

    """Configurable Parameters that can be overwritten by that defined JSON or YAML files.
    std_free_vcpus  standard deviation of free vCPU in all hypervisors
    std_free_ram    standard deviation of free memory in MB in all hypervisors
    std_free_disk   standard deviation of free disk in GB in all hypervisors
    match_host      sub-string of a nova-compute host
    """
    DEFAULT_CONFIG = {
        'std_free_vcpus': 100.0,
        'std_free_ram': 100000.0,
        'std_free_disk': 100000.0,
    }

    """Columns in pandas hypervisor usage table.
        All are selected fields from nova hypervisors object,
        except iteration and free_vcpus.
    """
    FIELDS = (
        'iteration',
        'id',
        'hypervisor_hostname',
        'current_workload',
        'running_vms',
        'vcpus',
        'vcpus_used',
        'free_vcpus',
        'memory_mb',
        'memory_mb_used',
        'free_ram_mb',
        'local_gb',
        'local_gb_used',
        'free_disk_gb',
    )

    """Columns in pandas computation result table.
        index is the iteration number
    """
    COLS = (
        'std_free_vcpus',
        'std_free_ram',
        'std_free_disk',
    )

    def __init__(self, criterion_value):
        """Discover configurable parameters and Rally task UUID.
           Create one nova client to be used through out testing.
           Find the list of active nova-compute hosts.
           Collect hypervisor usage before running any test.
        Instance Variables:
            admin       metadata of openstack admin
            all_com     pandas table with all computation results
            all_data    pandas table with all hypervisor usage
            diff_data   pandas table with hypervisor usage before and after tests
            index       index to pandas table
            it          iteration number, rally's ITER + 1
            hosts       list of nova-compute hosts
            nova        nova client
            one_com     pandas table with computation results for one iteration
            one_data    pandas table with hypervisor usage for one iteration
            list_com    list of computation results
            params      configurable parameters
                        criterion_value is from yaml or json
                        and overrides DEFAULT_CONFIG
            uuid        Rally task UUID
                        used as prefix for all data files
        """
        super(HypervisorUsage, self).__init__(criterion_value)
        self.params = dict(HypervisorUsage.DEFAULT_CONFIG.items() + self.criterion_value.items())
        task = db.task_get_detailed_last()
        self.uuid = task['uuid']
        self.admin = self._get_admin()
        self.nova = osclients.Clients(objects.Endpoint(**self.admin)).nova()
        self.hosts = self._get_hosts()
        self.index = 0
        self.it = 0
        self.one_data = None
        self.one_com = None
        self.list_com = [0.0, 0.0, 0.0]
        self.all_data = pd.DataFrame(columns=HypervisorUsage.FIELDS)
        self.all_com = pd.DataFrame(columns=HypervisorUsage.COLS)
        self._run_iteration()
        self.diff_data = pd.DataFrame(columns=HypervisorUsage.FIELDS)
        self.diff_data = pd.concat([self.diff_data, self.one_data])
        LOG.info("%s:%s() task: %s, params: %s",
                 self.__class__.__name__, sys._getframe().f_code.co_name, self.uuid, self.params)

    def add_iteration(self, iteration):
        """Collect hypervisor usage for each iteration.
        :params iteration: has following keys
            ['scenario_output', 'error', 'duration', 'timestamp', 'idle_duration', 'atomic_actions']
        """
        LOG.debug("%s:%s() %s", self.__class__.__name__, sys._getframe().f_code.co_name, iteration)
        self._run_iteration()
        try:
            if (self.list_com[0] > self.params['std_free_vcpus'] or
               self.list_com[1] > self.params['std_free_ram'] or
               self.list_com[2] > self.params['std_free_disk']):
                self.success = False
            else:
                self.success = True
        except Exception as e:
            LOG.exception(e)
            self.success = False
        finally:
            return self.success

    def details(self):
        """Return test results.
            Some version of pandas converts all integer to float in csv file.
        :returns results: message displayed on HTML page
        """
        self.diff_data = pd.concat([self.diff_data, self.one_data])
        results = self._results()
        self._report()
        return (_(results))

    def _run_iteration(self):
        """For each iteration,
            Collect hypervisor usage.
            Process collected data.
        """
        self._get_hypervisor_usage()
        self._process_usage()
        self.it = self.it + 1

    def _get_admin(self):
        """Get the admin metadata from active deployments,
            there is only one active deployment.
        :returns admin: metadata of admin user
        """
        deploys = db.deployment_list()
        LOG.debug("%s:%s() admin %s", self.__class__.__name__, sys._getframe().f_code.co_name, deploys[0].admin)
        return deploys[0].admin

    def _get_hosts(self):
        """Get the list of nova-compute hosts.
            Also see 'nova service-list'.
        In Icehouse:
            nova service object has state and status
            but nova hypervisor object does not
        In Kilo:
            nova hypervisor object has state and status
        List of keys in service object:
            [ '_info', '_loaded', 'binary', 'disabled_reason', 'host', 'id',
            'manager', 'state', 'status', 'updated_at', 'zone' ]
        :returns hosts: a list of nova-compute hosts
        """
        fields = ['binary', 'host', 'id', 'state', 'status']
        hosts = []
        try:
            objs = self.nova.services.list()
            for o in objs:
                d = {}
                for field in fields:
                    d[field] = getattr(o, field, '')
                LOG.debug("%s:%s() service: %s", self.__class__.__name__, sys._getframe().f_code.co_name, d)
                if d['binary'] == 'nova-compute' and d['state'] == 'up' and d['status'] == 'enabled':
                    host = d['host']
                    if 'match_host' not in self.params:
                        hosts.append(host)
                    else:
                        for match in self.params['match_host']:
                            if match in host:
                                hosts.append(host)
                                break
        except Exception as e:
            LOG.exception(e)
            raise
        finally:
            LOG.info("%s:%s() hosts: %s", self.__class__.__name__, sys._getframe().f_code.co_name, hosts)
            return hosts

    def _get_hypervisor_usage(self):
        """Get the hardware resource usage in each hypervisor.
            Also see 'nova hypervisor-list'
        List of keys in hypervisor objects in Icehouse:
            [ '_info', '_loaded', 'cpu_info', 'current_workload', 'disk_available_least',
            'free_disk_gb', 'free_ram_mb', 'host_ip', 'hypervisor_hostname', 'hypervisor_type',
            'hypervisor_version', 'id', 'local_gb', 'local_gb_used', 'manager', 'memory_mb',
            'memory_mb_used', 'running_vms', 'service', 'vcpus', 'vcpus_used' ]
        List of keys in hypervisor objects in Kilo:
            [ '_info', '_loaded', 'cpu_info', 'current_workload', 'disk_available_least',
            'free_disk_gb', 'free_ram_mb', 'host_ip', 'hypervisor_hostname', 'hypervisor_type',
            'hypervisor_version', 'id', 'local_gb', 'local_gb_used', 'manager', 'memory_mb',
            'memory_mb_used', 'running_vms', 'service', 'state', 'status', 'vcpus', 'vcpus_used' ]
        """
        try:
            self.one_data = pd.DataFrame(columns=HypervisorUsage.FIELDS)
            objs = self.nova.hypervisors.list()
            for o in objs:
                d = {}
                host = getattr(o, 'hypervisor_hostname', '')
                if host in self.hosts:
                    for field in HypervisorUsage.FIELDS:
                        d[field] = getattr(o, field, '')
                    self.one_data.loc[self.index] = [
                        self.it,
                        d['id'],
                        d['hypervisor_hostname'],
                        d['current_workload'],
                        d['running_vms'],
                        d['vcpus'],
                        d['vcpus_used'],
                        d['vcpus'] - d['vcpus_used'],
                        d['memory_mb'],
                        d['memory_mb_used'],
                        d['free_ram_mb'],
                        d['local_gb'],
                        d['local_gb_used'],
                        d['free_disk_gb'],
                    ]
                    LOG.debug("%s:%s() index %d: %s",
                              self.__class__.__name__, sys._getframe().f_code.co_name, self.index, d)
                    self.index = self.index + 1
            self.all_data = pd.concat([self.all_data, self.one_data])
        except Exception as e:
            LOG.exception(e)
            raise

    def _process_usage(self):
        """Process hypervisor usage from one iteration.
            pandas fails to compute STD if there is only one data sample in table
            so set STD to 0.0
        """
        self.one_com = pd.DataFrame(columns=HypervisorUsage.COLS)
        if len(self.one_data.index) == 1:
            self.one_com.loc[self.it] = [0.0, 0.0, 0.0]
        else:
            std = self.one_data[['free_vcpus', 'free_ram_mb', 'free_disk_gb']].std()
            self.list_com = std.values.tolist()
            self.one_com.loc[self.it] = self.list_com
        self.all_com = pd.concat([self.all_com, self.one_com])

    def _results(self):
        """Dump to STDOUT after testing.
        :returns results:   standard deviations of last iteration
        """
        results = "std_free_vcpus: %0.2f std_free_ram: %0.2f std_free_disk: %0.2f" % (
                  self.list_com[0], self.list_com[1], self.list_com[2])
        print "\n%s:%s(): %s" % (
            self.__class__.__name__, sys._getframe().f_code.co_name, results)
        return results

    def _report(self):
        """Dump information to STDOUT after testing.
        """
        if logging.is_debug():
            print "\n%s:%s(): Resource Usage" % (
                self.__class__.__name__, sys._getframe().f_code.co_name)
            print(self.all_data)
            print "\n%s:%s(): Computation Results" % (
                self.__class__.__name__, sys._getframe().f_code.co_name)
            print(self.all_com)
        data_file = report.get_hypervisor_file(self.uuid)
        diff_file = report.get_hypervisor_diff_file(self.uuid)
        com_file = report.get_hypervisor_std_file(self.uuid)
        self.all_data.to_csv(data_file, index=True)
        self.diff_data.to_csv(diff_file, index=True)
        self.all_com.to_csv(com_file, index=True)
        print "\n%s:%s(): Resource usage written to:\n\t%s" % (
            self.__class__.__name__, sys._getframe().f_code.co_name, data_file)
        print "\n%s:%s(): Resource usage before and after test written to:\n\t%s" % (
            self.__class__.__name__, sys._getframe().f_code.co_name, diff_file)
        print "\n%s:%s(): Computation results written to:\n\t%s" % (
            self.__class__.__name__, sys._getframe().f_code.co_name, com_file)
