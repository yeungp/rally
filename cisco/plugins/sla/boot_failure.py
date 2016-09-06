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
import json
import pdb

sys.path.append('/opt/rally/plugins/cisco/common')
import report
import lock

LOG = logging.getLogger(__name__)


@plugin.configure(name="boot_failure")
class BootFailure(sla.SLA):
    """Number of server that failed to boot.
    """
    CONFIG_SCHEMA = {
        "type": "object",
        "$schema": consts.JSON_SCHEMA,
        "properties": {
            "max": {
                "type": "integer",
                "minimum": 0,
            },
        }
    }

    """Configurable Parameters that can be overwritten by that defined JSON or YAML files.
    max     maximum number of servers that fail to boot
    """
    DEFAULT_CONFIG = {
        'max': 10000,
    }

    def __init__(self, criterion_value):
        """Create data file.
        Instance Variables:
            data_file   json file that holds information for each boot server 
            msg         message of check result
            params      configurable parameters
                        criterion_value is from yaml or json
                        and overrides DEFAULT_CONFIG
            task        rally task
        """
        super(BootFailure, self).__init__(criterion_value)
        self.params = dict(BootFailure.DEFAULT_CONFIG.items() + self.criterion_value.items())
        self.msg = ''
        task = db.task_get_detailed_last()
        self.data_file = report.get_boot_status_file(task['uuid'])
        open(self.data_file, 'w').close()
        LOG.info("%s:%s() task: %s, params: %s, file: %s",
                 self.__class__.__name__, sys._getframe().f_code.co_name,
                 task['uuid'], self.params, self.data_file)

    def add_iteration(self, iteration):
        """Collect hypervisor usage for each iteration.
        :params iteration: has following keys
            ['scenario_output', 'error', 'duration', 'timestamp', 'idle_duration', 'atomic_actions']
        """
        LOG.debug("%s:%s() %s", self.__class__.__name__, sys._getframe().f_code.co_name, iteration)
        fail = self._run_iteration()
        try:
            if fail > self.params['max']:
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
        :returns results: message displayed on HTML page
        """
        self._results()
        self._report()
        return (_(self.msg))

    def _run_iteration(self):
        """For each iteration,
            Check number of boot failure.
        """
        boot = 0
        fail = 0
        try:
            with open(self.data_file, 'r') as f:
                for l in f.readlines():
                    d = json.loads(l)
                    if not d['state'] == 'active':
                        fail = fail + 1
                    boot = boot + 1
            self.msg = "boot %d servers with %d failure" % (boot, fail)
        except Exception as e:
            LOG.exception(e)
            raise
        finally:
            return fail

    def _results(self):
        """Dump results to STDOUT after testing.
        """
        print "%s:%s(): %s" % (
            self.__class__.__name__, sys._getframe().f_code.co_name, self.msg)

    def _report(self):
        """Dump information to STDOUT after testing.
        """
        print "\n%s:%s(): VM status written to:\n\t%s" % (
            self.__class__.__name__, sys._getframe().f_code.co_name, self.data_file)
