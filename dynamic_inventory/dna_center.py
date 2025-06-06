# Copyright (c) 2019 World Wide Technology
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

from __future__ import (absolute_import, division, print_function)
__metaclass__ = type

DOCUMENTATION = r'''
    name: dna_center
    plugin_type: inventory
    short_description: Returns Inventory from DNA Center
    description:
        - Retrieves inventory from DNA Center
        - Adds inventory to ansible working inventory
    extends_documentation_fragment:
        - constructed
    options:
        plugin:  
            description: Name of the plugin
            required: true
            choices: ['dna_center']
        host: 
            description: FQDN of the target host 
            required: true
            env:
                - name: DNAC_HOST
        dnac_version:
            description: DNAC PythonSDK requires a supported DNAC version key
            required: true
        username: 
            description: user credential for target system 
            required: true
            env:
                - name: DNAC_USERNAME
        password: 
            description: user pass for the target system
            required: true
            env:
                - name: DNAC_PASSWORD
        validate_certs: 
            description: certificate validation
            required: false
            default: true
            choices: [true, false]
        use_dnac_mgmt_int: 
            description: use the dnac mgmt interface as `ansible_host`
            required: false
            default: true
            choices: [true, false]
        toplevel: 
            description: toplevel group to add groups/hosts to ansible inventory
            required: false
        api_record_limit:
            description: DNAC API calls return maximum of <api_record_limit> records per invocation. Defaults to 500 records
            required: true
        hostname_filter:
            description: DNAC search query based on hostname
            required: false
        device_family:
            description: DNAC device family
            required: false
            default: 
                - Switches and Hubs
                - Routers
        location_name:
            descriotion: DNAC location name
            required: false
'''

EXAMPLES = r'''
    ansible-inventory --graph
    
    ansible-inventory --list 
'''

from ansible.errors import AnsibleError, AnsibleParserError
from ansible.module_utils._text import to_bytes, to_native
from ansible.parsing.utils.addresses import parse_address
from ansible.plugins.inventory import BaseInventoryPlugin, Constructable

import json
import sys
import math 

try: 
    import requests, urllib3
    from dnacentersdk import DNACenterAPI
    from dnacentersdk import ApiError
except ImportError as e:
    raise AnsibleError('Python requests module is required for this plugin. Error: %s' % to_native(e))

class InventoryModule(BaseInventoryPlugin, Constructable):

    NAME = 'dna_center'

    def __init__(self):
        super(InventoryModule, self).__init__()

        # from config 
        self.username = None
        self.password = None
        self.host = None
        self.dnac_version = None
        # self.session = None
        self.use_dnac_mgmt_int = None
        self.toplevel = None
        self.api_record_limit = 500
        self.hostname_filter = None
        self.device_family = None
        self.location_name = None
        
        # global attributes 
        self._site_list = None
        self._inventory = []
        self._host_list = None
        self._dnac_api = None

    def _login(self):
        '''
            :return Login results from the request.
        '''

        if not self.validate_certs:
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

        try:
            self._dnac_api = DNACenterAPI(
                username=self.username, 
                password=self.password, 
                base_url='https://' + self.host, 
                version=self.dnac_version,
                verify=self.validate_certs)
        except ApiError as e:
            raise AnsibleError('failed to login to DNA Center: %s' % to_native(e))
            
            return self._dnac_api

    def _get_inventory(self):
        '''
            :return The json output from the request object response. 
        '''

        try:
            device_count = (self._dnac_api.devices.get_device_count()).response
        except ApiError as e: 
            raise AnsibleParserError('Getting device count failed:  %s' % to_native(e))

        # calculate the number of API calls (ie pages) in case if device count
        # exceeds the api_record_limit
        offset_pages = math.ceil(device_count / self.api_record_limit)

        for offset in range(offset_pages):
            # DNAC API takes starting index of a device in a list
            # beginning with index of '1'
            start_index = offset * self.api_record_limit + 1
            try:
                inventory_results = (self._dnac_api.devices.get_device_list(
                    limit=self.api_record_limit, 
                    offset=start_index,
                    hostname=self.hostname_filter,
                    family=self.device_family,
                    location_name=self.location_name).response)
            except ApiError as e:
                raise AnsibleParserError('Getting device inventory failed:  %s' % to_native(e))

            self._inventory = [*self._inventory, *inventory_results]

        return self._inventory

    def _get_hosts(self):
        '''
             :param inventory A list of dictionaries representing the entire DNA Center inventory. 
             :return A List of tuples that include the management IP, device hostnanme, and the unique indentifier of the device.
        '''

        host_list = []

        for host in self._inventory: 
            # do not inventorize Access Points
            if host['family'].find('Unified AP') == -1: 
                host_dict = {}
                host_dict.update({
                    'managementIpAddress': host['managementIpAddress'],
                    'hostname' : host['hostname'],
                    'id': host['id'],
                    'os': (host['softwareType'] if host['family'].find('Unified AP') == -1 else host['family']), 
                    'version': host['softwareVersion'], 
                    'reachabilityStatus': host['reachabilityStatus'],
                    'role': host['role'],
                    'serialNumber': host['serialNumber'].split(', '),
                    'series': host['series'],
                    'host_data': host
                })
                host_list.append(host_dict)
        
        self._host_list = host_list
        
        return host_list

    def _get_sites(self):
        '''
            :return A list of tuples for sites containing the site name and the unique ID of the site.
        '''

        try:
            sites = (self._dnac_api.topology.get_site_topology()).response.sites
        except ApiError as e:
            raise AnsibleError('Getting site topology failed:  %s' % to_native(e))
        
        site_list = []
        site_dict = {}

        for site in sites: 

            special_char_map = { ord('ä'):'ae', ord('ü'):'ue', ord('ö'):'oe', ord('ß'):'ss', ord('('):'_', ord(')'):'_', ord(' '): '_', ord('-'):'_', ord('.'): '_' }
            normalized_site_name = site['name'].translate(special_char_map).lower()
            
            site_dict = {}
            if(site['locationType'] == 'building'):
                site_dict.update({'name': "bld_"+normalized_site_name, 'id': site['id'], 'parentId': site['parentId']})
            else:
                site_dict.update({'name': normalized_site_name, 'id': site['id'], 'parentId': site['parentId']})
            site_list.append(site_dict)
        
        self._site_list = site_list
        
        return site_list


    def _get_member_site(self, device_id):
        '''
            :param device_id: The unique identifier of the target device.
            :return A single string representing the name of the SITE group of which the device is a member.
        '''

        try:
            devices = (self._dnac_api.topology.get_physical_topology()).response.nodes
        except ApiError as e:
            raise AnsibleError('Getting member site failed: %s' % to_native(e))
        
        # Get the one device we are looking for
        device = [ dev for dev in devices if dev['id'] == device_id ][0]

        # Extract the siteid from the device data 
        site_id = device.get('additionalInfo').get('siteid')
        
        # set the site name from the self._site_list
        site_name = [ site['name'] for site in self._site_list if site['id'] == site_id ]

        # return the name if it exists
        if len(site_name) == 1:
            return site_name[0]
        elif len(site_name) == 0: 
            return 'ungrouped'
            

    def _add_sites(self):
        ''' Add groups and associate them with parent groups
            :param site_list: list of group dictionaries containing name, id, parentId
        '''
            
        # Global is a system group and the parent of all top level groups
        site_ids = [ ste['id'] for ste in self._site_list ]
        parent_name = ''

        if self.toplevel:
            self.inventory.add_group(self.toplevel)
        
        # Add all sites
        for site in self._site_list: 
            self.inventory.add_group(site['name'])

        # Add parent/child relationship
        for site in self._site_list: 
            
            if site['parentId'] in site_ids:
                parent_name = [ ste['name'] for ste in self._site_list if ste['id'] == site['parentId'] ][0]
                try: 
                    self.inventory.add_child(parent_name, site['name'])
                except Exception as e:
                    raise AnsibleParserError('adding child sites failed:  {} \n {}:{}'.format(e,site['name'],parent_name))
            elif self.toplevel:
                try: 
                    self.inventory.add_child(self.toplevel, site['name'])
                except Exception as e:
                    raise AnsibleParserError('adding child sites failed:  {} \n {}:{}'.format(e,site['name'],parent_name))
                


    def _add_hosts(self):
        """
            Add the devicies from DNAC Inventory to the Ansible Inventory
            :param host_list: list of dictionaries for hosts retrieved from DNAC

        """
        for h in self._host_list: 
            site_name = self._get_member_site( h['id'] )
            if site_name:
                host_name = self.inventory.add_host(h['hostname'], group=site_name)
                
                #  add variables to the hosts
                if self.use_dnac_mgmt_int:
                    self.inventory.set_variable(host_name,'ansible_host',h['managementIpAddress'])

                self.inventory.set_variable(host_name, 'os', h['os'])
                self.inventory.set_variable(host_name, 'version', h['version'])
                self.inventory.set_variable(host_name, 'reachability_status', h['reachabilityStatus'])
                self.inventory.set_variable(host_name, 'serial_number', h['serialNumber'])
                self.inventory.set_variable(host_name, 'hw_type', h['series'])
                # DNAC API calls operate on id of each managed element
                self.inventory.set_variable(host_name, 'id', h['id'])
                self.inventory.set_variable(host_name, 'site', site_name)
                self.inventory.set_variable(host_name, 'host_data', h['host_data'])

                if h['os'].lower() in ['ios', 'ios-xe', 'unified ap']:
                    self.inventory.set_variable(host_name, 'ansible_network_os', 'ios')
                    self.inventory.set_variable(host_name, 'ansible_connection', 'network_cli')
                    self.inventory.set_variable(host_name, 'ansible_become', 'yes')
                    self.inventory.set_variable(host_name, 'ansible_become_method', 'enable')
                elif h['os'].lower() in ['nxos','nx-os']:
                    self.inventory.set_variable(host_name, 'ansible_network_os', 'nxos')
                    self.inventory.set_variable(host_name, 'ansible_connection', 'network_cli')
                    self.inventory.set_variable(host_name, 'ansible_become', 'yes')
                    self.inventory.set_variable(host_name, 'ansible_become_method', 'enable')
            
                self._set_composite_vars(self.get_option('compose'), self.inventory.get_host(host_name).get_vars(), host_name, self.strict)
                self._add_host_to_composed_groups(self.get_option('groups'), dict(), host_name, self.strict)
                self._add_host_to_keyed_groups(self.get_option('keyed_groups'), dict(), host_name, self.strict)
            else:
                raise AnsibleError('no site name found for host: {} with site_id {}'.format(h['id'], self._site_list))




    def verify_file(self, path):
        
        ''' return true/false if this is possibly a valid file for this plugin to consume '''
        valid = False
        if super(InventoryModule, self).verify_file(path):
            # base class verifies that file exists and is readable by current user
            if path.endswith(('dna_center.yml')):
                valid = True
        return valid


    def parse(self, inventory, loader, path, cache=True):
        
        super(InventoryModule, self).parse(inventory, loader, path, cache)

        # initializes variables read from the config file based on the documentation string definition. 
        #  if the options are not defined in the docstring, the are not imported from config file
        self._read_config_data(path)

        # Set options values from configuration file
        try:
            self.host = self.get_option('host')
            self.dnac_version = self.get_option('dnac_version')
            self.username = self.get_option('username')
            self.password = self.get_option('password')
            self.use_dnac_mgmt_int = self.get_option('use_dnac_mgmt_int')
            self.validate_certs = self.get_option('validate_certs')
            self.toplevel = self.get_option('toplevel')
            self.api_record_limit = self.get_option('api_record_limit')
            self.strict = self.get_option('strict')
            self.hostname_filter = self.get_option('hostname_filter')
            self.device_family = self.get_option('device_family')
            self.location_name = self.get_option('location_name')
        except Exception as e: 
            raise AnsibleParserError('getting options failed:  %s' % to_native(e))

        # Attempt login to DNAC
        self._login()

        # Obtain Inventory Data
        self._get_inventory()
      
        # Add groups to the inventory 
        self._get_sites()
        self._add_sites()
        
        # Add the hosts to the inventory 
        self._get_hosts()
        self._add_hosts()