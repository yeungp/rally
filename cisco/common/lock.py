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
import fcntl

class Lock(object):
    """Named semaphore handled by linux kernel
    to synchronize resoures between independent user space processes.
    """
    
    def __init__(self, lock_file):
        """Open the lock file.
            Create lock file if it does not exist already.
        Instance Variables:
            fd          file descriptor
            lock_file   named semaphore
        :param lock_file: name of lock file
        """
        self.lock_file = lock_file
        self.fd = open(self.lock_file, 'w')
    
    def __del__(self):
        """Close the lock file.
        """
        self.fd.close()

    def lock_shared(self):
        """Non blocking shared lock.
        May raise IOError
        """
        return fcntl.flock(self.fd, fcntl.LOCK_SH | fcntl.LOCK_NB)

    def lock_shared_blocking(self):
        """Blocking shared lock.
        """
        return fcntl.flock(self.fd, fcntl.LOCK_SH)

    def lock_exclusive(self):
        """Non blocking exclusive lock.
        May raise IOError
        """
        return fcntl.flock(self.fd, fcntl.LOCK_EX | fcntl.LOCK_NB)

    def lock_exclusive_blocking(self):
        """Blocking exclusive lock.
        """
        return fcntl.flock(self.fd, fcntl.LOCK_SH)

    def unlock(self):
        """Non blocking remove lock.
        """
        return fcntl.flock(self.fd, fcntl.LOCK_UN | fcntl.LOCK_NB)

    def unlock_blocking(self):
        """Blocking remove lock.
        """
        return fcntl.flock(self.fd, fcntl.LOCK_UN)
        
