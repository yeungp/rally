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

import os

DIR = "/tmp/"

def get_aggregate_file(uuid):
    """Get full path filename to write aggregate information.
    :param uuid:    Rally task UUID
    """
    return DIR + uuid + "-aggregate.json"

def get_boot_status_file(uuid):
    """Get full path filename to read or write boot status data.
    :param uuid:    Rally task UUID
    """
    return DIR + uuid + "-boot-status.json"

def get_boot_status_lock(uuid):
    """Get full path filename to lock boot status data file.
    :param uuid:    Rally task UUID
    """
    return DIR + uuid + "-nova-scheduler.lock"

def get_hypervisor_file(uuid):
    """Get full path filename to write resource usage in hypervisors.
    :param uuid:    Rally task UUID
    """
    return DIR + uuid + "-hypervisor-usage.csv"

def get_hypervisor_diff_file(uuid):
    """Get full path filename to write pre and post test resource usage in hypervisors.
    :param uuid:    Rally task UUID
    """
    return DIR + uuid + "-hypervisor-usage-diff.csv"

def get_hypervisor_std_file(uuid):
    """Get full path filename to write standard deviation of resource usage in hypervisors.
    :param uuid:    Rally task UUID
    """
    return DIR + uuid + "-hypervisor-usage-std.csv"
