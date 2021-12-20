#!/usr/bin/python3

import subprocess
import uuid
import os.path

from do_automate.util import *
from do_automate.globals import *
from do_automate.do_qemu import auto_qemu
from do_automate.do_softROCE import softROCE

MAC_ADDR_PREFIX = "52:54:00:12:43:"

class post_boot_configuration:
	def __init__(self, log_obj,  dac_object):
		self.log_obj = log_obj
		self.dac_obj = dac_object

		self.dau_obj = da_util(self.log_obj, self.dac_obj)
		self.my_roce = softROCE(self.log_obj)

	def __log(self, log_level, *args):
		message = self.__class__.__name__ + ": "
		for arg in args:
			message += str(arg) + " "

		self.log_obj.log(log_level, message)


	def __vm_configure_share_modules(self, my_ip, shared_9p_tag):
		command = "rm -rf /mnt/shared_modules/"
		status, status_string = self.dac_obj.run_command_remote(command, my_ip)
		if not status:
			self.__log(ERROR, status_string)
			return False

		command = "mkdir /mnt/shared_modules"
		status, status_string = self.dac_obj.run_command_remote(command, my_ip)
		if not status:
			self.__log(ERROR, status_string)
			return False

		command = "mount -t 9p -o trans=virtio {st} /mnt/shared_modules -oversion=9p2000.L".format(st = shared_9p_tag)
		status, status_string = self.dac_obj.run_command_remote(command, my_ip)
		if not status:
			self.__log(ERROR, status_string)
			return False

		command = "ln -s -f /mnt/shared_modules/lib/modules/*/ /lib/modules/"
		status, status_string = self.dac_obj.run_command_remote(command, my_ip)
		if not status:
			self.__log(ERROR, status_string)
			return False

		return True

	def fixed_pbc(self, list_of_ips, username, password, shared_9p_tag):
		# ping test
		for my_ip in list_of_ips:
			self.__log(INFO, "Checking connectivity to ", my_ip)
			if not self.dau_obj.ping_check(50, my_ip):
				self.__log(ERROR, "ping failed")
				return False
			self.__log(INFO, "Passed!\n")

		self.__log(INFO, "Configuring shared folder for modules")
		if not self.__vm_configure_share_modules(list_of_ips[0], shared_9p_tag):
			self.__log(ERROR, "__vm_configure_share_modules() failed")
			return False
		self.__log(INFO, "Done!\n")

		self.__log(INFO, "Inserting required modules in the VM")
		# Insert null_blk module. Some tests expect the module to be already inserted
		command = "modprobe null_blk nr_devices=5"
		status, status_string = self.dac_obj.run_sudo_command_remote(command, list_of_ips[0])
		if not status:
			self.__log(ERROR, status_string)
			return False

		# Insert ram block module. Some tests expect the module to be already inserted
		command = "modprobe brd rd_nr=5 rd_size=204800"
		status, status_string = self.dac_obj.run_sudo_command_remote(command, list_of_ips[0])
		if not status:
			self.__log(ERROR, status_string)
			return False
		self.__log(INFO, "Done!\n")

		# Insert ram block module. Some tests expect the module to be already inserted
		command = "modprobe loop"
		status, status_string = self.dac_obj.run_sudo_command_remote(command, list_of_ips[0])
		if not status:
			self.__log(ERROR, status_string)
			return False
		self.__log(INFO, "Done!\n")

		for i in range(len(list_of_ips)):
			my_ip = list_of_ips[i]
			self.__log(INFO, "Starting softROCE configuration on IP {ip}".format(ip = my_ip))

			# Temp
			# The actual configuration should have the same device name for both interfaces,
			# but on different ports
			rdma_dev_name = "mlx4_" + str(i)

			# Configure softROCE on the interface
			if not self.my_roce.setup_softroce(username, password, my_ip, rdma_dev_name):
				self.__log(ERROR, "SoftROCE configuration Failed!")

		return True

	def optional_pbc(self):
		pass


# Storage consts
STOR_LINUX_KERNEL_FOLDER = "/stor_linux/"
STOR_VM_SHARE_FOLDER = "/stor_vm_share/"
STOR_SHARED_9P_TAG = "storehost"

# Server consts
SERV_LINUX_KERNEL_FOLDER = "/serv_linux/"
SERV_VM_SHARE_FOLDER = "/serv_vm_share/"
SERV_SHARED_9P_TAG = "serverhost"

class da_vm_class:
	def __init__(self, log_obj):
		# Ready for spinning up VMs?
		self.vm_params_set = False

		# Set up log stuff
		self.log_obj = log_obj
		self.dac_obj = da_command(self.log_obj)
		self.dag_obj = da_get(self.log_obj, self.dac_obj)
		self.dau_obj = da_util(self.log_obj, self.dac_obj)

		self.pbc_obj = post_boot_configuration(self.log_obj, self.dac_obj)

		self.__log(DEBUG, "In constructor")
		self.__log(INFO, "Storage object created")

	def __log(self, log_level, *args):
		message = self.__class__.__name__ + ": "
		for arg in args:
			message += str(arg) + " "

		self.log_obj.log(log_level, message)

	def __create_default_folders(self):
		command = "mkdir -p {folder1} {folder2}".format(folder1 = self.linux_kernel_folder,
				folder2 = self.vm_share_folder)
		try:
			s = subprocess.check_output([command], stderr=subprocess.DEVNULL, shell=True).decode('utf-8')
			returncode = 0
		except subprocess.CalledProcessError as e:
			self.__log(DEBUG, "Fail!")
			return False

		return True

	def __generate_vm_uuids(self):
		num_of_vm = self.vm_params_dict['num_of_vm']
		all_uuids = []

		for i in range(num_of_vm):
			vm_uuid = str(uuid.uuid4())
			while vm_uuid in self.vm_dict_cur.keys() and vm_uuid in all_uuids:
				vm_uuid = uuid.uuid4()
			all_uuids.append(vm_uuid)

		return all_uuids

	def __mac_addr_used(self, mac_addr):
		command = "arp -n | grep {mac_addr}".format(mac_addr = mac_addr)
		status, status_string = self.dac_obj.run_command_local(command)
		if status or mac_addr not in status_string.rstrip():
			for vm_details in self.vm_dict_cur.values():
				if mac_addr in vm_details["macs"]:
					return True
			self.__log(DEBUG, "Mac addr {mac_addr} not being used".format(mac_addr = mac_addr), status_string)
			return False

		return True

	def __generate_vm_macs(self):
		num_of_vm = self.vm_params_dict['num_of_vm']
		all_macs = []

		i = 0
		octet = 10
		while i < NUM_OF_ETH_INT * num_of_vm:
			this_mac_addr = MAC_ADDR_PREFIX + str(octet)
			if not self.__mac_addr_used(this_mac_addr):
				all_macs.append(this_mac_addr)
				i += 1
			octet += 1
			if octet == 100:
				self.__log(ERROR, "__generate_vm_macs() failed.")
				return False

		return all_macs

	def __check_and_copy_imgs(self, num_of_vm, qcow, vm_class):
		common_qcow = os.path.basename(qcow)

		all_imgs = []
		next_avail_pers_slot = 0
		for i in range(num_of_vm):
			while next_avail_pers_slot in self.used_pers_slots:
				next_avail_pers_slot += 1
			self.curr_pers_slots.append(next_avail_pers_slot)
			img_path = os.path.join(IMGS_FODLER, vm_class, str(next_avail_pers_slot), common_qcow)
			if os.path.exists(img_path):
				self.__log(INFO, ("{} exist, no copy.".format(img_path)))
			else:
				dir = os.path.dirname(img_path)
				command = "mkdir -p {dir} && cp {src} {dst}".format(dir=dir, src=qcow, dst=img_path)
				status, status_string = self.dac_obj.run_command_local(command)
				if status:
					self.__log(ERROR, status, status_string)
					return False
			all_imgs.append(img_path)
			next_avail_pers_slot += 1

		return all_imgs

	def __create_vm_dict_aq(self, vm_params_dict):
		self.__log(DEBUG, "In __create_vm_dict_aq: vm_params_dict = ", vm_params_dict)
		vm_dict_aq = {}

		vm_params_dict['qcow'] = self.dau_obj.check_and_make_path_abs(vm_params_dict['qcow'])

		try:
			vm_dict_aq['type'] = vm_params_dict['type']
			vm_dict_aq['num_of_vm'] = vm_params_dict['num_of_vm']
			vm_dict_aq['num_of_cpu'] = vm_params_dict['num_of_cpu']
			vm_dict_aq['ram_size'] = vm_params_dict['ram_size']
			vm_dict_aq['block_dev'] = vm_params_dict['block_dev']
			vm_dict_aq['username'] = vm_params_dict['username']
			vm_dict_aq['password'] = vm_params_dict['password']
			vm_dict_aq['bridges'] = vm_params_dict['bridges']
			vm_dict_aq['kernel_code'] = vm_params_dict['kernel_code']
			vm_dict_aq['mode'] = vm_params_dict['mode']
		except KeyError:
			self.__log(ERROR, "Key error: vm_params_dict incomplete")
			return False

		if "modules" in vm_params_dict:
			vm_dict_aq['modules'] = vm_params_dict['modules']

		if "optional" in vm_params_dict:
			vm_dict_aq['optional'] = vm_params_dict['optional']

		if "scsi_images" in vm_params_dict:
			for i in range(len(vm_params_dict['scsi_images'])):
				vm_params_dict['scsi_images'][i] = self.dau_obj.check_and_make_path_abs(vm_params_dict['scsi_images'][i])

			vm_dict_aq['scsi_images'] = []
			if vm_params_dict["mode"] == "persistent":
				for img in vm_params_dict['scsi_images']:
					img_abs = self.dau_obj.check_and_make_path_abs(img)
					vm_dict_aq['scsi_images'].append(self.__check_and_copy_imgs(vm_dict_aq['num_of_vm'], img_abs, vm_dict_aq['type']))
			else:
				for img in vm_params_dict['scsi_images']:
					loi = []
					for i in range(vm_params_dict['num_of_vm']):
						loi.append(img)
					vm_dict_aq['scsi_images'].append(loi)

		if vm_params_dict["mode"] == "persistent":
			# We ignore the slots update by scsi imgae copy
			self.curr_pers_slots = []
			vm_dict_aq['qcow'] = self.__check_and_copy_imgs(vm_dict_aq['num_of_vm'], vm_params_dict['qcow'], vm_dict_aq['type'])
		else:
			vm_dict_aq['qcow'] = []
			for i in range(vm_params_dict['num_of_vm']):
				self.curr_pers_slots.append(i)
				vm_dict_aq['qcow'].append(vm_params_dict['qcow'])

		return vm_dict_aq

	def __add_new_vm_details(self, all_ips, all_pids):
		num_of_vm = self.vm_params_dict['num_of_vm']

		for i in range(num_of_vm):
			this_vm_details = {}

			this_vm_details['mode'] = self.vm_params_dict["mode"]
			this_vm_details['vm_type'] = self.vm_params_dict["type"]
			this_vm_details['vm_num'] = self.curr_pers_slots[i]
			this_vm_details['vm_name'] = this_vm_details['vm_type'] + "_" + str(this_vm_details['vm_num'])
			this_vm_details['kernel_code'] = self.vm_params_dict['kernel_code']
			this_vm_details['ips'] = all_ips[i]
			this_vm_details['pid'] = all_pids[i]
			this_vm_details['state'] = "Network Up"
			this_vm_details['macs'] = [self.all_macs[(i*NUM_OF_ETH_INT)+0], self.all_macs[(i*NUM_OF_ETH_INT)+1]]
			this_vm_details['bridges'] = self.vm_params_dict['bridges']
			this_vm_details['shared_9p_tag'] = self.shared_9p_tag
			this_vm_details['base_image'] = self.vm_dict_aq['qcow'][i]

			if "scsi_images" in self.vm_dict_aq:
				this_vm_details['scsi_images'] = []
				for scsi_img in self.vm_dict_aq['scsi_images']:
					this_vm_details['scsi_images'].append(scsi_img[i])

			this_vm_details['optional'] = self.vm_params_dict["optional"]

			self.vm_dict_cur[self.vm_dict_aq["uuids"][i]] = this_vm_details

		return True

	def __remove_vm_details(self, vm_uuid):
		del self.vm_dict_cur[vm_uuid]

	def set_vm_params(self, vm_params_dict, build_option):
		self.__log(DEBUG, "In set_vm_params")

		# VM details of currently running VMs
		self.vm_dict_cur = self.dau_obj.read_and_update_vm_dict()
		if self.vm_dict_cur is False:
			self.__log(ERROR, "read_and_update_vm_dict() failed: ", self.vm_dict_cur)
			return False

		# Already used slots
		self.used_pers_slots = []
		for vm_details in self.vm_dict_cur.values():
			if vm_details['vm_type'] != vm_params_dict['type']:
				continue

			if vm_details['mode'] == "persistent":
				self.used_pers_slots.append(int(vm_details["vm_num"]))

		# Slots used for this run
		self.curr_pers_slots = []

		# Information given by main
		self.vm_params_dict = vm_params_dict
		self.vm_class = vm_params_dict["type"]

		if "optional" not in self.vm_params_dict:
			self.vm_params_dict["optional"] = []

		self.username = vm_params_dict['username']
		self.password = vm_params_dict['password']

		self.dac_obj.set_param(self.username, self.password)

		# Generate VM specific, unique IDs
		self.all_uuids = self.__generate_vm_uuids()
		self.all_macs = self.__generate_vm_macs()

		# Since each class would need its own space to work on share with VM
		# Configure vm_class specific folder
		if self.vm_class == "storage":
			self.linux_kernel_folder = default_data_path + STOR_LINUX_KERNEL_FOLDER
			self.vm_share_folder = default_data_path + STOR_VM_SHARE_FOLDER
			self.shared_9p_tag = STOR_SHARED_9P_TAG
		elif self.vm_class == "server":
			self.linux_kernel_folder = default_data_path + SERV_LINUX_KERNEL_FOLDER
			self.vm_share_folder = default_data_path + SERV_VM_SHARE_FOLDER
			self.shared_9p_tag = SERV_SHARED_9P_TAG
		else:
			self.__log(ERROR, "vm_class unknown: ", self.vm_class)

		if not self.__create_default_folders():
			self.__log(ERROR, "Creating default folders failed")
			return False

		# Create the auto_qemu object
		self.my_qemu = auto_qemu(self.log_obj, self.linux_kernel_folder, self.vm_share_folder, self.shared_9p_tag)

		# Process stuff like scsi_image qcow path, etc
		self.vm_dict_aq = self.__create_vm_dict_aq(vm_params_dict)
		if not self.vm_dict_aq:
			self.__log(ERROR, "Creating dict for auto_qemu failed.")
			return False
		self.__log(DEBUG, "In set_vm_params: vm_dict_aq = ", self.vm_dict_aq)

		# Add the unique IDs generated before to vm_dict to be passed to auto_qemu
		self.vm_dict_aq["uuids"] = self.all_uuids
		self.vm_dict_aq["macs"] = self.all_macs

		if not self.my_qemu.set_vm_params(self.vm_dict_aq, build_option):
			self.__log(ERROR, "set_vm_params failed.")
			return False

		# Now start_auto can be called for this object
		self.vm_params_set = True
		return True

	def start_auto(self, host_password):
		self.__log(DEBUG, "In start_auto")
		self.__log(INFO, "Calling auto_qemu to start VMs")

		if not self.vm_params_set:
			self.__log(ERROR, "start_auto called before calling set_vm_params.")
			return False

		# One call to set_vm_params should be followed by one call to start_auto
		# To call start_auto again, call set_vm_params again with relevant info
		self.vm_params_set = False

		# Send the start VM command
		all_info = self.my_qemu.start_auto(host_password)
		if not all_info:
			self.__log(INFO, "start_auto failed.")
			return False

		all_ips = all_info["all_ips"]
		all_pids = all_info["all_pids"]

		# Do post boot configurations
		for list_of_ips in all_ips:
			if not self.pbc_obj.fixed_pbc(list_of_ips, self.username, self.password, self.shared_9p_tag):
				self.__log(INFO, "fixed_pbc failed.")
				return False

		self.vm_dict_cur = self.dau_obj.read_and_update_vm_dict()
		if self.vm_dict_cur is False:
			self.__log(ERROR, "read_and_update_vm_dict() failed: ", self.vm_dict_cur)
			return False

		if not self.__add_new_vm_details(all_ips, all_pids):
			self.__log(ERROR, "__add_new_vm_details() failed: ")
			return False

		if not self.dau_obj.save_vm_details_to_json(self.vm_dict_cur):
			self.__log(ERROR, "save_vm_details_to_json failed: ")
			return False

		return all_ips

	def shutdown_vm(self, vm_ip, username, password, host_password):
		'''
		Sending a shutdown command and checking status is tricky
		Sometimes the command executes successfully, but the system goes down
		way too fast to send a successful return status and status_string.
		So we are gonna rely on ping to confirm the shutdown
		'''
		self.dac_obj.set_param(username, password, host_password)

		self.vm_dict_cur = self.dau_obj.read_and_update_vm_dict()
		if self.vm_dict_cur is False:
			self.__log(ERROR, "read_and_update_vm_dict() failed: ", self.vm_dict_cur)
			return False

		vm_uuids = []
		if vm_ip == "all" or vm_ip == "a":
			for uuid, vm_details_list in self.vm_dict_cur.items():
				vm_uuids.append(uuid)
		else:
			for uuid, vm_details_list in self.vm_dict_cur.items():
				if vm_ip in vm_details_list["ips"]:
					vm_uuids.append(uuid)
					break

		if not vm_uuids:
			self.__log(ERROR, "shutdown_vm failed. No matching VM found")
			return False

		for this_vm_uuid in vm_uuids:
			this_vm_detail = self.vm_dict_cur[this_vm_uuid]
			vm_ip = this_vm_detail["ips"][0]

			if "pipe" in this_vm_detail["optional"]:
				self.pipe = True
			else:
				self.pipe = False

			self.__log(INFO, "Shutting down VM with ip {ip}".format(ip = vm_ip))

			command = "shutdown -h now"
			# if self.dau_obj.ping_check(1, vm_ip):
			status, status_string = self.dac_obj.run_sudo_command_remote(command, vm_ip)
			if not status:
				# In case, log this for debuggging
				self.__log(DEBUG, status_string)
			'''
			else:
				self.__log(INFO, "Ping failed. Attempting to shutdown through pipe console")
				status, status_string = self.dac_obj.run_sudo_command_remote_pipe(this_uuid, command, 3)
				if not status:
					# In case, log this for debuggging
					self.__log(DEBUG, status_string)
			'''

			self.__remove_vm_details(this_vm_uuid)

		if not self.dau_obj.save_vm_details_to_json(self.vm_dict_cur):
			self.__log(ERROR, "save_vm_details_to_json failed: ")
			return False

		self.__log(INFO, "Done!")
		return True

	def reboot_vm(self, vm_ip, username, password, host_password):
		self.username = username
		self.password = password

		self.dac_obj.set_param(username, password, host_password)

		self.vm_dict_cur = self.dau_obj.read_and_update_vm_dict()
		if self.vm_dict_cur is False:
			self.__log(ERROR, "read_and_update_vm_dict() failed: ", self.vm_dict_cur)
			return False

		vm_uuids = []
		if vm_ip == "all" or vm_ip == "a":
			for uuid, vm_details_list in self.vm_dict_cur.items():
				vm_uuids.append(uuid)
		else:
			for uuid, vm_details_list in self.vm_dict_cur.items():
				if vm_ip in vm_details_list["ips"]:
					vm_uuids.append(uuid)
					break

		if not vm_uuids:
			self.__log(ERROR, "shutdown_vm failed. No matching VM found")
			return False

		for this_vm_uuid in vm_uuids:
			this_vm_detail = self.vm_dict_cur[this_vm_uuid]
			vm_ip = this_vm_detail["ips"][0]

			if "pipe" in this_vm_detail["optional"]:
				self.pipe = True
			else:
				self.pipe = False

			self.shared_9p_tag = this_vm_detail["shared_9p_tag"]

			self.__log(INFO, "Getting MAC of all network devices for VM with IP {ip}".format(ip = vm_ip))

			command = "reboot"
			#if self.dau_obj.ping_check(1, vm_ip):
			all_macs = self.dag_obj.get_mac_of_all_interfaces(vm_ip)
			if not all_macs:
				self.__log(ERROR, "get_mac_of_all_interfaces() Failed")
				return False

			self.__log(INFO, "Rebooting VM with ip {ip}".format(ip = vm_ip))
			status, status_string = self.dac_obj.run_sudo_command_remote(command, vm_ip)
			if not status:
				# In case, log this for debuggging
				self.__log(DEBUG, status_string)
			'''
			else:
				# Networking seems to be down. Try reboot through pipe console
				all_macs = vm_dict[this_uuid]["mac"]

				self.__log(INFO, "Ping failed. Attempting to reboot through pipe console")
				status, status_string = self.dac_obj.run_sudo_command_remote_pipe(this_uuid, command, 3)
				if not status:
					# In case, log this for debuggging
					self.__log(DEBUG, status_string)
			'''

			# Breathe
			time.sleep(5)

			list_of_ips = []

			self.__log(INFO, "Attempting to get all the IPs of the VM through mac addrs")
			for my_mac_addr in all_macs:
				my_ip = self.dag_obj.get_ip_from_mac(my_mac_addr)
				if my_ip is None:
					self.__log(ERROR, "Cannot find IP of the launched VM.")
					return False
				list_of_ips.append(my_ip)

			'''
			if not self.__login_to_vm_pipe(this_uuid):
				self.__log(DEBUG, "__login_to_vm_pipe Failed")
				return False

			if not self.__verify_pipe_comm(this_uuid):
				self.__log(DEBUG, "__verify_pipe_comm Failed")
				return False
			'''

			self.__log(INFO, "Performing post boot configuration for {ip}".format(ip = vm_ip))
			if not self.pbc_obj.fixed_pbc(list_of_ips, self.username, self.password, self.shared_9p_tag):
				self.__log(INFO, "fixed_pbc failed.")
				return False

		return True

