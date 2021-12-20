#!/usr/bin/python3

import subprocess
import time
import sys
import numbers
from urllib.parse import urlparse

from do_automate.globals import *
from do_automate.util import *

# GLOBALS
qemu_cmd = "qemu-system-x86_64 {kvm_option} -smp {cpu} -m {ram}M -nographic {mode} \
		-monitor unix:{monitor_file},server,nowait \
		-drive id=d0,file={qcow_image},if=none,format=qcow2 \
		-device virtio-blk-pci,drive=d0,scsi=off -kernel {bzImage} \
		-append 'root=/dev/{blk_dev} rw console=ttyS0' \
		-netdev bridge,br={bridge_1},id=id0 -device virtio-net,netdev=id0,mac={mac_addr_1} \
		-netdev bridge,br={bridge_2},id=id1 -device virtio-net,netdev=id1,mac={mac_addr_2} \
		-virtfs local,path={vm_share_folder},mount_tag={shared_9p_tag},security_model=passthrough,id=d1,readonly \
		{optional_qemu_args}"

basic_modules = [
"CONFIG_NETWORK_FILESYSTEMS",
"CONFIG_EXT4_FS",
"CONFIG_IA32_EMULATION",
"CONFIG_PCI",
"CONFIG_VIRTIO_PCI",
"CONFIG_VIRTIO",
"CONFIG_VIRTIO_BALLOON",
"CONFIG_VIRTIO_BLK",
"CONFIG_VIRTIO_NET",
"CONFIG_NET_9P",
"CONFIG_NET_9P_VIRTIO",
"CONFIG_9P_FS",
"CONFIG_9P_FS_POSIX_ACL",
"CONFIG_E100",
"CONFIG_E1000",
"CONFIG_E1000E",
"CONFIG_NET_FAILOVER",
]

class auto_qemu:
	def __init__(self, log_obj, linux_kernel_folder = None, vm_share_folder = None, shared_9p_tag = None):
		# The default folder where the linux code with be checked out in case a git url is supplied
		# When local kernel code is to be used, this is overridden
		self.linux_kernel_folder = linux_kernel_folder

		# Folder which will contain the installed modules.
		# This folder will be shared with the VM
		self.vm_share_folder = vm_share_folder

		self.shared_9p_tag = shared_9p_tag

		# Set up log stuff
		self.log_obj = log_obj
		# I should really clean this up, and use proper python logging object

		# Helper objects
		self.dac_obj = da_command(self.log_obj)
		self.dag_obj = da_get(self.log_obj, self.dac_obj)
		self.dau_obj = da_util(self.log_obj, self.dac_obj)

		# Ready for spinning up VMs?
		self.vm_params_set = False

		self.__log(DEBUG, "In constructor")
		self.__log(INFO, "Current directory : ", current_directory)

	def __log(self, log_level, *args):
		message = self.__class__.__name__ + ": "
		for arg in args:
			message += str(arg) + " "

		self.log_obj.log(log_level, message)

	def set_vm_params(self, vm_params_dict, build_option):
		'''
			The vm_params_dict should look something like this

			vm_params_dict = {'mode': mode, 'num_of_vm': num,
                                        'num_of_cpu': cpus,
                                        'ram_size': ram,
                                        'qcow': qcow,
                                        'block_dev': block_dev,
                                        'username': username,
                                        'password': password,
                                        'bridges': [bridge_1, bridge_2],
                                        'kernel_code': kernel_code,
                                        'modules': modules_install }
		'''
		if (not self.linux_kernel_folder) or (not self.vm_share_folder) or (not self.shared_9p_tag):
			self.__log(INFO, "Please instantiate the do_qemu object with valid values")
			return False

		self.type = vm_params_dict["type"]

		# VM count and related config
		try:
			self.num_of_vm = int(vm_params_dict['num_of_vm'])
		except ValueError:
			self.__log(INFO, "Erroneous value in num_of_vm field")
			return False
		self.vm_cpus = vm_params_dict['num_of_cpu']
		self.vm_ram = vm_params_dict['ram_size']

		# Reading the main configs
		self.qcow_image = vm_params_dict['qcow']
		self.block_dev = vm_params_dict['block_dev']
		self.my_username = vm_params_dict['username']
		self.my_password = vm_params_dict['password']

		self.dac_obj.set_param(self.my_username, self.my_password)

		# bridges
		self.bridge_1 = vm_params_dict['bridges'][0]
		self.bridge_2 = vm_params_dict['bridges'][1]

		self.kernel_code = vm_params_dict['kernel_code']
		self.local_kernel_code = True
		url_check = urlparse(self.kernel_code)
		try:
			if all([url_check.scheme, url_check.netloc]):
				self.local_kernel_code = False
		except ValueError:
			self.local_kernel_code = True

		if "modules" in vm_params_dict:
			self.modules_install = vm_params_dict['modules']
		else:
			self.modules_install = []

		# Optional args
		self.pipe = False
		if "optional" in vm_params_dict:
			# List of options
			opt = vm_params_dict['optional']
			if "pipe" in opt:
				self.pipe = True

		self.vm_uuids = vm_params_dict["uuids"]
		self.all_mac_addrs = vm_params_dict["macs"]

		# Init some default values
		self.bzImage = self.linux_kernel_folder + "/bzImage"
		self.host_password = ""
		self.all_ips = []
		self.all_pids = []

		# This is used to store the dictionary containing uuid to vm_details mapping.
		# VM details include ip, mac and bridges
		self.vm_details_dict = {}

		self.build_option = build_option

		self.mode = vm_params_dict["mode"]

		self.the_modules = basic_modules.copy()
		if "scsi_images" in vm_params_dict:
			self.the_modules.extend(["CONFIG_SCSI", "CONFIG_BLK_DEV_SD", "CONFIG_MEGARAID_SAS"])
			self.scsi_images = vm_params_dict["scsi_images"]
		else:
			self.scsi_images = []

		# Do some sanity checks
		if not self.__sanity_check():
			self.__log(ERROR, "Sanity check failed")
			return False

		self.__log(DEBUG, "Got VM parameters: ")
		self.__log(DEBUG, self.num_of_vm, self.vm_cpus, self.vm_ram)
		self.__log(DEBUG, self.my_username, self.my_password)
		self.__log(DEBUG, self.kernel_code, self.qcow_image, self.block_dev, self.bridge_1, self.bridge_2, self.my_username, self.my_password)

		self.vm_params_set = True

		return True

	def __sanity_check(self):
		# Do some sanity checks
		if not isinstance(self.vm_cpus, numbers.Integral) or not isinstance(self.vm_ram, numbers.Integral):
			self.__log(ERROR, "cpu/ram field value erroneous")
			return False

		for vm_num in range(self.num_of_vm):
			if not self.qcow_image[vm_num] or "qcow" not in self.qcow_image[vm_num]:
				self.__log(ERROR, "qcow image error")
				return False

		if not self.block_dev:
			self.__log(ERROR, "No block device")
			return False

		if not self.my_username:
			self.__log(ERROR, "No username")
			return False

		# We dont need to check for both the bridges
		if not self.bridge_1:
			self.__log(ERROR, "No bridge given")
			return False

		return True

	def __check_host_dependencies(self):
		self.__log(DEBUG, "Checking host dependencies")
		command = "dpkg -s qemu"
		status, status_string = self.dac_obj.run_command_local(command)
		if status:
			self.__log(ERROR, "Fail! ", status_string)
			return False

		command = "ip -o -4 a | grep {bridge} | awk '{{print $2}}'".format(bridge = self.bridge_1)
		status, status_string = self.dac_obj.run_command_local(command)
		if status or status_string.rstrip() != self.bridge_1:
			self.__log(ERROR, "Fail! Network bridge {bridge} not found".format(bridge = self.bridge_1), status_string)
			return False

		if self.bridge_1 != self.bridge_2:
			command = "ip -o -4 a | grep {bridge} | awk '{{print $2}}'".format(bridge = self.bridge_2)
			status, status_string = self.dac_obj.run_command_local(command)
			if status or status_string.rstrip() != self.bridge_2:
				self.__log(ERROR, "Fail! Network bridge {bridge} not found".format(bridge = self.bridge_2), status_string)
				return False

		if "virbr" not in self.bridge_1 or "virbr" not in self.bridge_2:
			self.__log(0, "Be aware that you are not using the default virbr bridge")

		# TODO
		# Add dependency check for kernel make tools
		# flex bison openssl libssl-dev dkms libelf-dev libudev-dev libpci-dev libiberty-dev autoconf

		return True

	def __check_vm_dependencies(self, my_ip):
		command = "dpkg -s openssh-server"
		status, status_string = self.dac_obj.run_command_remote(command, my_ip)
		if not status:
			self.__log(ERROR, status_string)
			return False

		# Verify that ssh service is running
		command = "systemctl status ssh"
		status, status_string = self.dac_obj.run_sudo_command_remote(command, my_ip)
		if not status:
			self.__log(ERROR, status_string)
			return False

		return True

	def __create_pipe_files(self, uuid):
		if not self.pipe:
			return True

		command = "mkfifo {pipe_folder}/{uuid}.in {pipe_folder}/{uuid}.out".format(pipe_folder = PIPES_FOLDER, uuid = uuid)
		status, status_string = self.dac_obj.run_command_local(command)
		if status:
			self.__log(ERROR, status, status_string)
			return False
		return True

	def __delete_pipe_files(self, uuid):
		if not self.pipe:
			return True

		command = "rm {pipe_folder}/{uuid}.in {pipe_folder}/{uuid}.out".format(pipe_folder = PIPES_FOLDER, uuid = uuid)
		status, status_string = self.dac_obj.run_command_local(command)
		if status:
			self.__log(ERROR, "Problem deleting stale pipe files ", status, status_string)
			# Lets not fail here. It really isnt a big deal that rm failed.
		return True


	def __install_ext_module(self, module_path):
		self.__log(INFO, "Doing make and install of external module ", module_path)
		# For some reason "make -C" option does not work for IBNBD
		command = "cd {folder} && make KDIR={linux_kernel_folder}".format(folder = module_path, linux_kernel_folder = self.linux_kernel_folder)
		status, status_string = self.dac_obj.run_command_local(command)
		if status:
			self.__log(ERROR, status, status_string)
			return False

		command = "cd {folder} && make INSTALL_MOD_PATH={vm_share_folder} KDIR={linux_kernel_folder} modules_install".format(
				folder = module_path, vm_share_folder = self.vm_share_folder, linux_kernel_folder = self.linux_kernel_folder)
		status, status_string = self.dac_obj.run_command_local(command)
		if status:
			self.__log(ERROR, status, status_string)
			return False

		return True

	def __login_to_vm_pipe(self, uuid):
		if not self.pipe:
			return True

		global vm_comm_delay_mult

		status_string = "this passes butter"
		this_pipe_in = PIPES_FOLDER + "/" + uuid + ".in"
		this_pipe_out = PIPES_FOLDER + "/" + uuid + ".out"

		# Flush all the bootup logs till the login console is launched
		while status_string and "login:" not in status_string[-10:]:
			command = "timeout 5 cat {pipe}".format(pipe = this_pipe_out)
			status_string = self.dac_obj.run_sudo_command_local_ret_out(command)
			if not status_string:
				self.__log(DEBUG, "__run_sudo_command_local_ret_out Failed:", status_string)
				return False

		command = "{username}\n".format(username = self.my_username)
		try:
			with open(this_pipe_in, 'w') as f:
				f.write(command)
		except:
			self.__log(DEBUG, "__run_sudo_command_local Failed with Exception: " + str(sys.exc_info()[0]))
			return False

		time.sleep(1 * vm_comm_delay_mult)
		command = "{password}\n".format(password = self.my_password)
		try:
			with open(this_pipe_in, 'w') as f:
				f.write(command)
		except:
			self.__log(DEBUG, "__run_sudo_command_local Failed with Exception: " + str(sys.exc_info()[0]))
			return False
		time.sleep(1 * vm_comm_delay_mult)

		# Flush once more to keep the console clean
		command = "timeout {this_timeout} cat {pipe}".format(this_timeout = 3 * vm_comm_delay_mult, pipe = this_pipe_out)
		status_string = self.dac_obj.run_sudo_command_local_ret_out(command)
		self.__log(DEBUG, "status_string ", status_string)
		if not status_string:
			self.__log(DEBUG, "__run_sudo_command_local_ret_out Failed:", status_string)
			return False

		return True

	def __verify_pipe_comm(self, uuid):
		if not self.pipe:
			return True

		command = "uname -a"
		status, status_string = self.dac_obj.run_command_remote_pipe(uuid, command, 3)
		self.__log(DEBUG, "Verifying VM with uuid ", uuid, status, status_string)
		if not status:
			self.__log(ERROR, status, status_string)
			return False

		if "Linux" not in status_string:
			self.__log(ERROR, status, status_string)
			return False

		return True

	def __get_optional_qemu_args(self, vm_uuid, vm_num):
		all_args = ""

		if self.pipe:
			all_args += " -serial pipe:{pipe_file}".format(pipe_file = PIPES_FOLDER + str(vm_uuid))

			if not self.__create_pipe_files(vm_uuid):
				self.__log(DEBUG, "__create_pipe_files Failed")
				return False


		if self.scsi_images:
			all_args += " -device megasas,id=scsi0"
			img_id = 0
			for image in self.scsi_images:
				img_path = image[vm_num]
				all_args += " -device scsi-hd,drive=drive{d_id},bus=scsi0.0,channel=0,scsi-id={s_id},lun=0".format(d_id = img_id, s_id = img_id)
				all_args += " -drive file={img},if=none,id=drive{d_id}".format(img = img_path, d_id = img_id)
				img_id += 1

		return all_args

	def __spin_up_qemu_vm(self, vm_iter):
		vm_uuid = self.vm_uuids[vm_iter]

		qemu_mode = ""
		if self.mode == "snapshot":
			qemu_mode = "-snapshot"

		# Check if the host system is a VM or not
		kvm_enable = ""
		command = "dmesg | grep -i Hypervisor"
		status, status_string = self.dac_obj.run_command_local(command)
		if status:
			kvm_enable = "-enable-kvm"

		opt_qemu_args = self.__get_optional_qemu_args(vm_uuid, vm_iter)

		cmd = qemu_cmd.format(kvm_option = kvm_enable, \
					cpu = self.vm_cpus, ram = self.vm_ram, \
					monitor_file = default_data_path + "vm_monitors/" + str(vm_uuid), \
					mode = qemu_mode, \
					qcow_image = self.qcow_image[vm_iter], \
					bzImage = self.bzImage, blk_dev = self.block_dev, \
					mac_addr_1 = str(self.all_mac_addrs[(vm_iter*NUM_OF_ETH_INT)+0]), \
					mac_addr_2 = str(self.all_mac_addrs[(vm_iter*NUM_OF_ETH_INT)+1]), \
					bridge_1 = self.bridge_1, bridge_2 = self.bridge_2, \
					vm_share_folder = self.vm_share_folder, \
					shared_9p_tag = self.shared_9p_tag, \
					optional_qemu_args = opt_qemu_args)

		self.__log(INFO, "Starting VM with command: {cmd}\n".format(cmd = cmd))

		pid = self.dac_obj.run_sudo_command_local_get_pid(cmd)

		# Dont ask why +2
		self.all_pids.append(pid+2)

		return True

	def __generate_vm_details(self, vm_iter):
		my_mac_addr = []
		list_of_ips = [None, None]
		vm_uuid = self.vm_uuids[vm_iter]

		self.__log(INFO, "Attempting to get IPs and verify pipes communication of the launched VM")
		for i in range(NUM_OF_ETH_INT):
			my_mac_addr.append(str(self.all_mac_addrs[(vm_iter*NUM_OF_ETH_INT)+i]))
			my_ip = self.dag_obj.get_ip_from_mac(my_mac_addr[i])
			if my_ip is None:
				self.__log(ERROR, "Cannot find IP of the launched VM.\nIs the bridge configured properly?")
				self.__log(ERROR, "Manual check required. Exiting")
				return False
			list_of_ips[i] = my_ip
			self.__log(DEBUG, "Done! IP: {ip}\n".format(ip = my_ip))

		if not self.__login_to_vm_pipe(vm_uuid):
			self.__log(DEBUG, "__login_to_vm_pipe Failed")
			return False

		if not self.__verify_pipe_comm(vm_uuid):
			self.__log(DEBUG, "__verify_pipe_comm Failed")
			return False

		# VM up and running, now create the details dict to be stored
		this_vm_details = {}
		this_vm_details['ip'] = list_of_ips
		this_vm_details['mac'] = [my_mac_addr[0], my_mac_addr[1]]
		this_vm_details['bridges'] = [self.bridge_1, self.bridge_2]
		this_vm_details['shared_9p_tag'] = self.shared_9p_tag
		this_vm_details['img'] = self.qcow_image[vm_iter]
		this_vm_details['optional'] = []

		if self.pipe:
			this_vm_details['optional'].append("pipe")

		# Update our vm_details_dict and json
		self.vm_details_dict[vm_uuid] = this_vm_details

		return this_vm_details

	def __add_kernel_config_options(self, list_of_options):

		all_lines = []
		for the_mod in list_of_options:
			this_str = the_mod + "=y\n"
			all_lines.append(this_str)

		try:
			with open(default_data_path + "/.config-fragment", 'w') as f:
				f.writelines(all_lines)
		except:
			self.__log(ERROR, "Something went wrong while saving .config-fragment file")
			return False

		command = "cd {kernel_folder} && bash ./scripts/kconfig/merge_config.sh .config \
				{default_data_folder}/.config-fragment".format( \
				kernel_folder = self.linux_kernel_folder, default_data_folder = default_data_path)
		status, status_string = self.dac_obj.run_command_local(command)
		if status:
			self.__log(ERROR, status, status_string)
			return False

		return True

	def __check_kernel_config_file(self):
		try:
			with open(self.linux_kernel_folder + "/.config") as f:
				all_lines = f.readlines()
		except FileNotFoundError:
			self.__log(ERROR, ".config file not found in kernel folder")
			return False

		the_modules_copy = self.the_modules.copy()
		for i in range(len(all_lines)):
			this_str = all_lines[i]
			for the_mod in self.the_modules:
				if the_mod in this_str:
					if the_mod + "=" == this_str[:-2]:
						if this_str[-2:] != "y\n":
							# This option is not set to y, lets change that
							this_str = this_str[:-2] + "y\n"
							all_lines[i] = this_str
							self.__log(INFO, "Changed module option: ", this_str[:-1])
						the_modules_copy.remove(the_mod)
						break
					elif "not set" in this_str:
						if the_mod in this_str.split(' '):
							# This option is not set at all, lets change that
							this_str = the_mod + "=y\n"
							all_lines[i] = this_str
							the_modules_copy.remove(the_mod)
							self.__log(INFO, "Changed module option: ", this_str[:-1])
							break

		try:
			with open(self.linux_kernel_folder + "/.config", 'w') as f:
				f.writelines(all_lines)
		except:
			self.__log(ERROR, "Something went wrong while saving .config file")
			return False

		if the_modules_copy:
			self.__log(INFO, "The following module options were not found at all", the_modules_copy)
			self.__log(INFO, "Attempting to add those options")
			if not self.__add_kernel_config_options(the_modules_copy):
				self.__log(ERROR, "__add_kernel_config_options() Failed")
				return False
			# Recurse
			if not self.__check_kernel_config_file():
				self.__log(ERROR, "__check_kernel_config_file recurse failed")
				return False

		return True

	def __clone_git_repo(self):
		# Delete folder if already exists
		command = "rm -rf {folder}/".format(folder = self.linux_kernel_folder)
		status, status_string = self.dac_obj.run_command_local(command)
		if status:
			self.__log(ERROR, status, status_string)
			return False

		# create the folder
		command = "mkdir -p {folder}".format(folder = self.linux_kernel_folder)
		status, status_string = self.dac_obj.run_command_local(command)
		if status:
			self.__log(ERROR, status, status_string)
			return False
		self.__log(INFO, "Main folder for cloning: {path}".format(path = self.linux_kernel_folder))

		# Confirm that the folder exists
		command = "ls {folder}".format(folder = self.linux_kernel_folder)
		status, status_string = self.dac_obj.run_command_local(command)
		if status:
			self.__log(ERROR, status, status_string)
			return False

		self.__log(INFO, "Cloning the repo {repo} into {folder}".format(repo = self.kernel_code, folder = self.linux_kernel_folder))
		# clone repo into TMP_PATH
		command = "git clone --depth=1 {repo} {folder}".format(repo = self.kernel_code, folder = self.linux_kernel_folder)
		status, status_string = self.dac_obj.run_command_local(command)
		if status:
			self.__log(ERROR, status, status_string)
			return False
		self.__log(INFO, "Done cloning.\n")

		# copy the default config file to the linux folder
		command = "cp /boot/config-$(uname -r) {folder}/.config".format(folder = self.linux_kernel_folder)
		status, status_string = self.dac_obj.run_command_local(command)
		if status:
			self.__log(ERROR, status, status_string)
			return False
		self.__log(INFO, "Done!\n")

		return True

	def __build_kernel_code(self):
		self.__log(INFO, "Starting the make process")
		self.__log(INFO, "This may take some time, so sit back.")

		# Start the make
		command = "yes '' | make -C {folder} -j$(nproc)".format(folder = self.linux_kernel_folder)
		status, status_string = self.dac_obj.run_command_local(command)
		if status:
			self.__log(ERROR, status, status_string)
			return False

		self.__log(INFO, "Done make. Copying the bzImage to default data folder for step 2")

		# copy bzImage to the default path folder for step 2
		command = "cp {folder}/arch/x86_64/boot/bzImage {path}".format(folder = self.linux_kernel_folder, path = self.bzImage)
		status, status_string = self.dac_obj.run_command_local(command)
		if status:
			self.__log(ERROR, status, status_string)
			return False
		self.__log(INFO, "Got the bzImage.\n")

		# Delete vm_share folder if already exists
		command = "rm -rf {folder}/".format(folder = self.vm_share_folder)
		status, status_string = self.dac_obj.run_command_local(command)
		if status:
			self.__log(ERROR, status, status_string)
			return False

		# create vm_share folder
		command = "mkdir -p {folder}".format(folder = self.vm_share_folder)
		status, status_string = self.dac_obj.run_command_local(command)
		if status:
			self.__log(ERROR, status, status_string)
			return False
		self.__log(INFO, "Folder shared with the VM: {path}".format(path = self.vm_share_folder))

		self.__log(INFO, "Installing modules to shared folder")
		# Do modules_install to vm_share folder so that it can be shared with the VM
		command = "make -C {folder} INSTALL_MOD_PATH={vm_share_folder} modules_install".format(folder = self.linux_kernel_folder, vm_share_folder = self.vm_share_folder)
		status, status_string = self.dac_obj.run_command_local(command)
		if status:
			self.__log(ERROR, status, status_string)
			return False
		self.__log(INFO, "modules_install done.\n")

		return True

	def __build_and_create_image(self):
		'''
		Starting step 1
		This function gets the linux code from the git repo
		and builds the bzImage for the VMs
		'''

		if self.local_kernel_code:
			# This is path to the local folder which has the kernel code
			self.linux_kernel_folder = self.dau_obj.check_and_make_path_abs(self.kernel_code)
		else:
			if not self.__clone_git_repo():
				self.__log(ERROR, "__clone_git_repo failed")
				return False

		# check and configure the .config file
		if not self.__check_kernel_config_file():
			self.__log(ERROR, "__check_kernel_config_file failed")
			return False

		if not self.__build_kernel_code():
			self.__log(ERROR, "__build_kernel_code failed")
			return False

		return True

	def __launch_vms(self):
		self.__log(INFO, "Number of VMs to be launched: {vm_num}\n".format(vm_num = self.num_of_vm))

		for i in range(self.num_of_vm):
			# Run the command
			if not self.__spin_up_qemu_vm(i):
				self.__log(ERROR, "Spinning up VM failed")
			# Let qemu breath
			time.sleep(1)

		for i in range(self.num_of_vm):
			vm_details = self.__generate_vm_details(i)

			if (not vm_details):
				self.__log(ERROR, "self.__spin_up_qemu_vm() Failed")
				return False

			self.__log(INFO, "List of ips for the VM {vm_num} ".format(vm_num = i + 1), vm_details['ip'])

			# Append to list of ips
			self.all_ips.append(vm_details['ip'])

		return True

	def start_auto(self, host_password):
		if not self.vm_params_set:
			self.__log(ERROR, "VM params for this object not set correctly.")
			return False

		self.dac_obj.set_param(None, None, host_password)

		if not self.__check_host_dependencies():
			self.__log(ERROR, "Host dependency check failure")
			return False
		self.__log(INFO, "Host dependency check passed\n\n")

		if (self.build_option == "all" or self.build_option == "kernel") and self.kernel_code:
			self.__log(INFO, "******** Starting step 1 ********")
			self.__log(INFO, "This will take a long time..\n")
			if not self.__build_and_create_image():
				self.__log(ERROR, "Failure in step 1")
				return False
			self.__log(INFO, "******** Step 1 Finished ********\n")
		else:
			self.linux_kernel_folder = self.dau_obj.check_and_make_path_abs(self.kernel_code)
			self.__log(INFO, "Skip building kernel.")
			self.__log(INFO, "Skipping step 1\n")

		# Make and install given modules
		if (self.build_option == "all" or self.build_option == "module") and self.modules_install:
			self.__log(INFO, "Make and install given modules")
			for module in self.modules_install:
				if not self.dau_obj.is_path_absolute(module):
					module = current_directory + "/" + module
				if not self.__install_ext_module(module):
					self.__log(ERROR, "Failure during module installation")
					return False
			self.__log(INFO, "Done!\n")

		self.__log(INFO, "******** Starting step 2 ********")
		if not self.__launch_vms():
			# Should we check and shutdown VMs here?
			self.__log(ERROR, "Failure in step 2")
			return False
		self.__log(INFO, "******** Step 2 Finished ********\n\n")

		# TODO
		# Should we check RDMA ping connectivity across VMs?

		# Hack to print, irrespective of the log level
		self.__log(0, "List of IPs on the VMs")
		self.__log(0, self.all_ips)
		self.__log(INFO, "Shutdown the VMs after use")

		return {"all_ips": self.all_ips, "all_pids": self.all_pids}

	def build_new(self, config_file, git_repo):
		# If you have an existing object, and want to reinitialize it.
		self.__log(INFO, "Reconfiguring parameters from config file")
		self.__init__(config_file, git_repo)

if __name__ == "__main__":
	print("Do not call me directly, I am an introvert!")
