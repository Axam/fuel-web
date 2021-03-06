# Copyright 2014 Mirantis, Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import math

from fuel_agent.drivers import ks_spaces_validator
from fuel_agent import errors
from fuel_agent import objects
from fuel_agent.openstack.common import log as logging
from fuel_agent.utils import hardware_utils as hu

LOG = logging.getLogger(__name__)


def match_device(hu_disk, ks_disk):
    """Tries to figure out if hu_disk got from hu.list_block_devices
    and ks_spaces_disk given correspond to the same disk device. This
    is the simplified version of hu.match_device

    :param hu_disk: A dict representing disk device how
    it is given by list_block_devices method.
    :param ks_disk: A dict representing disk device according to
     ks_spaces format.

    :returns: True if hu_disk matches ks_spaces_disk else False.
    """
    uspec = hu_disk['uspec']

    # True if at least one by-id link matches ks_disk
    if ('DEVLINKS' in uspec and 'extra' in ks_disk
            and any(x.startswith('/dev/disk/by-id') for x in
                    set(uspec['DEVLINKS']) &
                    set(['/dev/%s' % l for l in ks_disk['extra']]))):
        return True

    # True if one of DEVLINKS matches ks_disk id
    if ('DEVLINKS' in uspec and 'id' in ks_disk
            and '/dev/%s' % ks_disk['id'] in uspec['DEVLINKS']):
        return True

    return False


class Nailgun(object):
    def __init__(self, data):
        # Here data is expected to be raw provisioning data
        # how it is given by nailgun
        self.data = data

    def partition_data(self):
        return self.data['ks_meta']['pm_data']['ks_spaces']

    @property
    def ks_disks(self):
        disk_filter = lambda x: x['type'] == 'disk' and x['size'] > 0
        return filter(disk_filter, self.partition_data())

    @property
    def ks_vgs(self):
        vg_filter = lambda x: x['type'] == 'vg'
        return filter(vg_filter, self.partition_data())

    @property
    def hu_disks(self):
        """Actual disks which are available on this node
        it is a list of dicts which are formatted other way than
        ks_spaces disks. To match both of those formats use
        _match_device method.
        """
        if not getattr(self, '_hu_disks', None):
            self._hu_disks = hu.list_block_devices(disks=True)
        return self._hu_disks

    def _disk_dev(self, ks_disk):
        # first we try to find a device that matches ks_disk
        # comparing by-id and by-path links
        matched = [hu_disk['device'] for hu_disk in self.hu_disks
                   if match_device(hu_disk, ks_disk)]
        # if we can not find a device by its by-id and by-path links
        # we try to find a device by its name
        fallback = [hu_disk['device'] for hu_disk in self.hu_disks
                    if '/dev/%s' % ks_disk['name'] == hu_disk['device']]
        found = matched or fallback
        if not found or len(found) > 1:
            raise errors.DiskNotFoundError(
                'Disk not found: %s' % ks_disk['name'])
        return found[0]

    def _getlabel(self, label):
        if not label:
            return ''
        # XFS will refuse to format a partition if the
        # disk label is > 12 characters.
        return ' -L {0} '.format(label[:12])

    def _get_partition_count(self, name):
        count = 0
        for disk in self.ks_disks:
            count += len([v for v in disk["volumes"]
                          if v.get('name') == name and v['size'] > 0])
        return count

    def _num_ceph_journals(self):
        return self._get_partition_count('cephjournal')

    def _num_ceph_osds(self):
        return self._get_partition_count('ceph')

    def partition_scheme(self):
        data = self.partition_data()
        ks_spaces_validator.validate(data)
        partition_scheme = objects.PartitionScheme()

        ceph_osds = self._num_ceph_osds()
        journals_left = ceph_osds
        ceph_journals = self._num_ceph_journals()

        for disk in self.ks_disks:
            parted = partition_scheme.add_parted(
                name=self._disk_dev(disk), label='gpt')
            # we install bootloader on every disk
            parted.install_bootloader = True
            # legacy boot partition
            parted.add_partition(size=24, flags=['bios_grub'])
            # uefi partition (for future use)
            parted.add_partition(size=200)

            for volume in disk['volumes']:
                if volume['size'] <= 0:
                    continue

                if volume.get('name') == 'cephjournal':
                    # We need to allocate a journal partition for each ceph OSD
                    # Determine the number of journal partitions we need on
                    # each device
                    ratio = math.ceil(float(ceph_osds) / ceph_journals)

                    # No more than 10GB will be allocated to a single journal
                    # partition
                    size = volume["size"] / ratio
                    if size > 10240:
                        size = 10240

                    # This will attempt to evenly spread partitions across
                    # multiple devices e.g. 5 osds with 2 journal devices will
                    # create 3 partitions on the first device and 2 on the
                    # second
                    if ratio < journals_left:
                        end = ratio
                    else:
                        end = journals_left

                    for i in range(0, end):
                        journals_left -= 1
                        if volume['type'] == 'partition':
                            prt = parted.add_partition(size=size)
                            if 'partition_guid' in volume:
                                prt.set_guid(volume['partition_guid'])
                    continue

                if volume['type'] in ('partition', 'pv', 'raid'):
                    prt = parted.add_partition(size=volume['size'])

                if volume['type'] == 'partition':
                    if 'partition_guid' in volume:
                        prt.set_guid(volume['partition_guid'])

                    if 'mount' in volume and volume['mount'] != 'none':
                        partition_scheme.add_fs(
                            device=prt.name, mount=volume['mount'],
                            fs_type=volume.get('file_system', 'xfs'),
                            fs_label=self._getlabel(volume.get('disk_label')))

                if volume['type'] == 'pv':
                    partition_scheme.vg_attach_by_name(
                        pvname=prt.name, vgname=volume['vg'])

                if volume['type'] == 'raid':
                    if 'mount' in volume and volume['mount'] != 'none':
                        partition_scheme.md_attach_by_mount(
                            device=prt.name, mount=volume['mount'],
                            fs_type=volume.get('file_system', 'xfs'),
                            fs_label=self._getlabel(volume.get('disk_label')))

            # this partition will be used to put there configdrive image
            if partition_scheme.configdrive_device() is None:
                parted.add_partition(size=20, configdrive=True)

        for vg in self.ks_vgs:
            for volume in vg['volumes']:
                if volume['size'] <= 0:
                    continue

                if volume['type'] == 'lv':
                    lv = partition_scheme.add_lv(name=volume['name'],
                                                 vgname=vg['id'],
                                                 size=volume['size'])

                    if 'mount' in volume and volume['mount'] != 'none':
                        partition_scheme.add_fs(
                            device=lv.device_name, mount=volume['mount'],
                            fs_type=volume.get('file_system', 'xfs'),
                            fs_label=self._getlabel(volume.get('disk_label')))

        partition_scheme.append_kernel_params(
            self.data['ks_meta']['pm_data']['kernel_params'])
        return partition_scheme

    def configdrive_scheme(self):
        data = self.data
        configdrive_scheme = objects.ConfigDriveScheme()

        admin_interface = filter(
            lambda x: (x['mac_address'] ==
                       data['kernel_options']['netcfg/choose_interface']),
            [dict(name=name, **spec) for name, spec
             in data['interfaces'].iteritems()])[0]
        configdrive_scheme.set_common(
            ssh_auth_key=data['ks_meta']['auth_key'],
            hostname=data['hostname'],
            fqdn=data['hostname'],
            name_servers=data['name_servers'],
            search_domain=data['name_servers_search'],
            master_ip=data['ks_meta']['master_ip'],
            master_url='http://%s:8000/api' % data['ks_meta']['master_ip'],
            udevrules=data['kernel_options']['udevrules'],
            admin_mac=data['kernel_options']['netcfg/choose_interface'],
            admin_ip=admin_interface['ip_address'],
            admin_mask=admin_interface['netmask'],
            admin_iface_name=admin_interface['name'],
            timezone=data['ks_meta']['timezone'],
        )

        configdrive_scheme.set_puppet(
            master=data['ks_meta']['puppet_master']
        )

        configdrive_scheme.set_mcollective(
            pskey=data['ks_meta']['mco_pskey'],
            vhost=data['ks_meta']['mco_vhost'],
            host=data['ks_meta']['mco_host'],
            user=data['ks_meta']['mco_user'],
            password=data['ks_meta']['mco_password'],
            connector=data['ks_meta']['mco_connector']
        )

        configdrive_scheme.set_profile(profile=data['profile'])
        return configdrive_scheme

    def image_scheme(self, partition_scheme):
        data = self.data
        image_scheme = objects.ImageScheme()
        # We assume for every file system user may provide a separate
        # file system image. For example if partitioning scheme has
        # /, /boot, /var/lib file systems then we will try to get images
        # for all those mount points. Images data are to be defined
        # at provision.json -> ['ks_meta']['image_data']
        for fs in partition_scheme.fss:
            if fs.mount not in data['ks_meta']['image_data']:
                continue
            image_data = data['ks_meta']['image_data'][fs.mount]
            image_scheme.add_image(
                uri=image_data['uri'],
                target_device=fs.device,
                # In the future we will get image_format and container format
                # from provision.json, but currently it is hard coded.
                image_format=image_data['format'],
                container=image_data['container'],
            )
        return image_scheme
