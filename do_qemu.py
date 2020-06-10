import sys
import yaml
import random
import subprocess
import time
from getpass import getpass
from datetime import datetime

from do_ssh import SSH
from do_softROCE import softROCE

# CONST
LINUX_KERNEL_FOLDER_NAME = "./data/linux/"
LOCAL_LOG_FOLDER = "./logs/"
ERROR = 1
INFO = 2
DEBUG = 3

# GLOBALS
qemu_cmd = "qemu-system-x86_64 -smp {cpu} -m {ram}M -nographic -snapshot -drive id=d0,file={qcow_image},if=none,format=qcow2 -device virtio-blk-pci,drive=d0,scsi=off -kernel {bzImage} -append 'root=/dev/{blk_dev}' -net nic,macaddr=52:54:00:12:43:{rand_octet} -net bridge,br={bridge}"

log_dict = {
  "ERROR": 1,
  "INFO": 2,
  "DEBUG": 3
}


class auto_qemu:
	def __init__(self, config_file):
		with open(config_file, 'r') as stream:
			cfg = yaml.safe_load(stream)

		self.main_cfg = cfg["main"]
		self.test_vm_cfg = cfg["test_vm_config"]

		# Reading the main configs
		self.git_repo = self.main_cfg['git_repo']
		self.qcow_image = self.main_cfg['qcow_image']
		self.block_dev = self.main_cfg['block_dev']
		self.bridge = self.main_cfg['bridge']
		self.my_username = self.main_cfg['vm_username']
		self.my_password = self.main_cfg['vm_password']

		# Some default values
		self.bzImage = "./data/bzImage"
		self.host_password = ""
		self.all_mac_octets = []
		self.all_ips = []

		# Set up log stuff
		self.local_log_file = LOCAL_LOG_FOLDER + "log_" + datetime.now().strftime('%Y-%m-%d_%H:%M:%S')
		self.log_level = self.main_cfg['log_level']
		# This log level is only for console.
		# In the file, everything gets logged. EVERYTHING!
		if self.log_level not in log_dict.keys():
			self.log_level = "INFO"
			print("Unknown Log level")
			print("Setting log level to INFO by default")
		self.log_level = log_dict[self.log_level]
		print("Log file ", self.local_log_file)

		# Helper objects
		self.my_ssh = SSH()
		self.my_roce = softROCE(self.local_log_file, self.log_level)
		# I should really clean this up, and use proper python logging object

		self.__log(DEBUG, "In constructor: Got")
		self.__log(DEBUG, self.git_repo, self.qcow_image, self.bridge, self.my_username, self.my_password)

	def __log(self, log_level, *args):
		message = self.__class__.__name__ + ": "
		for arg in args:
			message += str(arg) + " "

		# Write to console
		if self.log_level >= log_level:
			print(message)

		# Write to log file
		message = datetime.now().strftime('%Y-%m-%d\t%H:%M:%S\t').expandtabs(4) + message
		message += "\n"
		with open(self.local_log_file, 'a') as log_file:
			log_file.write(message)

	def __sanity_check(self):
		# Do some sanity checks
		if not self.qcow_image or "qcow" not in self.qcow_image:
			self.__log(ERROR, "qcow image error")
			return False

		if not self.block_dev:
			self.__log(ERROR, "No block device")
			return False

		if not self.bridge:
			self.__log(ERROR, "No bridge given")
			return False

		if not self.my_username or not self.my_password:
			self.__log(ERROR, "No VM username/password")
			return False

		if not self.test_vm_cfg["num_of_vm"]:
			self.__log(ERROR, "Number of VMs not provided in config file")
			return False

		if int(self.test_vm_cfg["num_of_vm"]) < 2:
			self.__log(ERROR, "Number of VMs for test should be atleast 2")
			return False

		return True

	def __run_command_remote(self, command, my_ip):
		# returns status, status_string
		# failure returns 0
		return self.my_ssh.run_command(self.my_username, self.my_password, my_ip, command)

	def __run_sudo_command_remote(self, command, my_ip):
		# returns status, status_string
		# failure returns 0
		return self.my_ssh.run_sudo_command(self.my_username, self.my_password, my_ip, command)

	def __run_command_local(self, command):
		try:
			s = subprocess.check_output([command], stderr=subprocess.DEVNULL, shell=True).decode('utf-8')
			returncode = 0
		except subprocess.CalledProcessError as e:
			s = e.output
			returncode = e.returncode
		# failure returns a positive returncode
		# success return 0 as returncode
		return returncode, s

	def __run_sudo_command_local(self, command):
		# TODO
		pass

	def __check_host_dependencies(self):
		self.__log(DEBUG, "Checking host dependencies")
		command = "dpkg -s qemu"
		self.__log(DEBUG, command)
		status, status_string = self.__run_command_local(command)
		if status:
			self.__log(DEBUG, "Fail! ", status_string)
			return False
		self.__log(DEBUG, "True")

		# TODO
		# Add dependency check for kernel make tools
		# flex bison openssl libssl-dev dkms libelf-dev libudev-dev libpci-dev libiberty-dev autoconf

		return True

	def __check_vm_dependencies(self, my_ip):
		command = "dpkg -s openssh-server"
		self.__log(DEBUG, command)
		status, status_string = self.__run_command_remote(command, my_ip)
		self.__log(DEBUG, status)
		if not status:
			self.__log(DEBUG, status_string)
			return False

		# Verify that ssh service is running
		command = "systemctl status ssh"
		self.__log(DEBUG, command)
		status, status_string = self.__run_sudo_command_remote(command, my_ip)
		self.__log(DEBUG, status)
		if not status:
			self.__log(DEBUG, status_string)
			return False

		return True

	def __get_ip_from_mac(self, my_mac_addr):
		command = "arp -n"
		ip_attempts = 0
		while ip_attempts < 10:
			self.__log(DEBUG, "Attempt", ip_attempts + 1)
			status, s = self.__run_command_local(command)
			if status:
				return None
			lines_list = s.split("\n")

			for line in lines_list:
				if my_mac_addr in line:
					return line[:line.index(" ")]
			ip_attempts += 1
			self.__log(DEBUG, "Failed! Waiting 60 seconds before next try\n")
			time.sleep(30)
		return None

	def __ping_check(self, ping_attempts, my_ip):
		command = "ping -c 4 {ip}".format(ip = my_ip)
		my_attempts = 0
		while my_attempts < ping_attempts:
			self.__log(DEBUG, "Attempt", my_attempts + 1)
			status, s = self.__run_command_local(command)
			if not status:
				return True
			my_attempts += 1
			self.__log(DEBUG, "Failed! Waiting 30 seconds before next try\n")
			time.sleep(30)
		return False

	def __shutdown_vm(self, vm_ip):
		'''
		Sending a shutdown command and checking status is tricky
		Sometimes the command executes successfully, but the system goes down
		way too fast to send a successful return status and status_string.
		So we are gonna rely on ping to confirm the shutdown
		'''
		shutdown_attempts = 0
		while shutdown_attempts < 5:
			command = "shutdown -h now"
			self.__log(DEBUG, command)
			status, status_string = self.__run_sudo_command_remote(command, vm_ip)
			time.sleep(120)
			if not self.__ping_check(1, vm_ip):
				self.__log(DEBUG, "Ping failed after shutdown. Shutdown successfull")
				return True
			shutdown_attempts += 1
			self.__log(DEBUG, "Trying shutdown again")
		self.__log(DEBUG, "Shutdown failed. Something is wrong.")
		return False

	def __spin_up_qemu_vm(self, command):
		command = "sudo -S " + command

		feed_password = subprocess.Popen("echo " + self.host_password, stdout=subprocess.PIPE, shell=True)
		status_string = subprocess.Popen(command, stdin=feed_password.stdout, stdout=subprocess.PIPE, shell=True)

		self.__log(DEBUG, "Popen called. Wait for 1 min.")
		self.__log(DEBUG, status_string, "\n")
		# waiting for a min for the vm to spin up
		time.sleep(60)
		return status_string

	def __prepare_cmd(self, test_vm_cfg):
		my_cpu = test_vm_cfg["cpu"]
		my_ram = test_vm_cfg["ram"]

		while True:
			my_rand_octet = random.randint(10, 99)
			if my_rand_octet not in self.all_mac_octets:
				self.all_mac_octets.append(my_rand_octet)
				break

		s = qemu_cmd.format(cpu = my_cpu, ram = my_ram, qcow_image = self.qcow_image, bzImage = self.bzImage, blk_dev = self.block_dev, rand_octet = my_rand_octet, bridge = self.bridge)
		return s

	def __build_git_create_image(self):
		'''
		Starting step 1
		This function gets the linux code from the git repo
		and builds the bzImage for the VMs
		'''

		# Delete folder if already exists
		command = "rm -rf {folder}/".format(folder = LINUX_KERNEL_FOLDER_NAME)
		self.__log(DEBUG, command)
		status, status_string = self.__run_command_local(command)
		if status:
			self.__log(DEBUG, status, status_string)
			return False
		self.__log(DEBUG, status_string)

		# create the folder
		command = "mkdir -p {folder}".format(folder = LINUX_KERNEL_FOLDER_NAME)
		self.__log(DEBUG, command)
		status, status_string = self.__run_command_local(command)
		if status:
			self.__log(DEBUG, status, status_string)
			return False
		self.__log(INFO, "Main folder for cloning: {path}".format(path = LINUX_KERNEL_FOLDER_NAME))

		# Confirm that the folder exists
		command = "ls {folder}".format(folder = LINUX_KERNEL_FOLDER_NAME)
		self.__log(DEBUG, command)
		status, status_string = self.__run_command_local(command)
		if status:
			self.__log(DEBUG, status, status_string)
			return False
		self.__log(DEBUG, status_string)

		self.__log(INFO, "Cloning the repo {repo} into {folder}".format(repo = self.git_repo, folder = LINUX_KERNEL_FOLDER_NAME))
		# clone repo into TMP_PATH
		command = "git clone {repo} {folder}".format(repo = self.git_repo, folder = LINUX_KERNEL_FOLDER_NAME)
		self.__log(DEBUG, command)
		status, status_string = self.__run_command_local(command)
		if status:
			self.__log(DEBUG, status, status_string)
			return False
		self.__log(DEBUG, status, status_string)
		self.__log(INFO, "Done cloning.\n")

		# Temporary patch
		# Apply patch to delay loading rnbd_server, and avoid the rtrs crash while boot
		command = "patch -d {folder} -p1 < ./data/fix_rtrs_crash.patch".format(folder = LINUX_KERNEL_FOLDER_NAME)
		self.__log(DEBUG, command)
		status, status_string = self.__run_command_local(command)
		if status:
			self.__log(DEBUG, status, status_string)
			return False
		self.__log(DEBUG, "Done: ", status_string)

		self.__log(INFO, "Starting the make process")
		self.__log(INFO, "This may take some time, so sit back.")

		# copy the default config file to the linux folder
		command = "cp ./default_kernel_config_file {folder}/.config".format(folder = LINUX_KERNEL_FOLDER_NAME)
		self.__log(DEBUG, command)
		status, status_string = self.__run_command_local(command)
		if status:
			self.__log(DEBUG, status, status_string)
			return False
		self.__log(DEBUG, "Done: ", status_string)

		# Start the make
		command = "yes '' | make -C {folder} -j$(nproc) bzImage".format(folder = LINUX_KERNEL_FOLDER_NAME)
		self.__log(DEBUG, command)
		status, status_string = self.__run_command_local(command)
		if status:
			self.__log(DEBUG, status, status_string)
			return False
		self.__log(DEBUG, "Done!")
		#self.__log(DEBUG, status_string)

		self.__log(INFO, "Done make. Copying the bzImage to data folder for step 2")

		# copy bzImage to our ./data/ folder for step 2
		command = "cp {folder}/arch/x86_64/boot/bzImage ./data/.".format(folder = LINUX_KERNEL_FOLDER_NAME)
		self.__log(DEBUG, command)
		status, status_string = self.__run_command_local(command)
		if status:
			self.__log(DEBUG, status, status_string)
			return False
		self.__log(DEBUG, "Done: ", status_string)
		self.__log(INFO, "Got the bzImage.\n")

		return True

	def __launch_vms(self, test_vm_cfg):
		# Check the number of VMs to be created
		if test_vm_cfg["num_of_vm"]:
			num_of_vm = test_vm_cfg["num_of_vm"]
		else:
			num_of_vm = 2

		self.__log(INFO, "Number of VMs to be launched: {vm_num}\n".format(vm_num = num_of_vm))

		for i in range(num_of_vm):
			my_cmd = self.__prepare_cmd(test_vm_cfg)

			# Run the command
			self.__log(INFO, "Starting VM {vm_num} with command: {cmd}\n".format(vm_num = i + 1, cmd = my_cmd))
			self.__spin_up_qemu_vm(my_cmd)

			mac_index = my_cmd.index("macaddr=")
			my_mac_addr = my_cmd[mac_index + 8:mac_index + 26]
			self.__log(DEBUG, my_mac_addr)

			# For testing
			#my_mac_addr = "52:54:00:12:35:00"
			#my_mac_addr = "52:54:00:12:43:12"
			#status_string = "In test mode"

			self.__log(INFO, "Attempting to get IP of the launched VM through mac addr")
			my_ip = self.__get_ip_from_mac(my_mac_addr)
			if my_ip is None:
				self.__log(ERROR, "Cannot find IP of the launched VM.\nIs the bridge configured properly?")
				self.__log(ERROR, "Manual check required. Exiting")
				return False
			self.__log(INFO, "Done! IP: {ip}\n".format(ip = my_ip))

			# ping test
			self.__log(INFO, "Checking connectivity to ", my_ip)
			if not self.__ping_check(10, my_ip):
				self.__log(ERROR, "ping failed")
				return False
			self.__log(INFO, "Passed!\n")

			# Configure softROCE on the interface
			self.__log(INFO, "Starting softROCE configuration on VM {vm_num}".format(vm_num = i + 1))
			if not self.my_roce.setup_softroce(self.my_username, self.my_password, my_ip):
				self.__log(ERROR, "SoftROCE configuration Failed!")
				return False
			self.__log(INFO, "Done!\n")

			# Append to list of ips
			self.all_ips.append(my_ip)

		return True

	def start_auto(self):
		# Do some sanity checks
		if not self.__sanity_check():
			self.__log(ERROR, "Sanity check failed")
			return False

		# Needed while invoking qemu
		print('Enter host password')
		self.host_password = getpass()
		print("")

		if not self.__check_host_dependencies():
			self.__log(ERROR, "Host dependency check failure")
			return False
		self.__log(INFO, "Host dependency check passed\n\n")

		if not self.git_repo:
			self.__log(INFO, "No git repo")
			self.__log(INFO, "Skipping step 1\n")
		else:
			self.__log(INFO, "******** Starting step 1 ********")
			self.__log(INFO, "This will take a long time..\n")
			if not self.__build_git_create_image():
				self.__log(ERROR, "Failure in step 1")
				return False
			self.__log(INFO, "******** Step 1 Finished ********\n")

		self.__log(INFO, "******** Starting step 2 ********")
		if not self.__launch_vms(self.test_vm_cfg):
			self.__log(ERROR, "Failure in step 2")
			return False
		self.__log(INFO, "******** Step 2 Finished ********\n\n")

		# TODO
		# Should we check RDMA ping connectivity across VMs?

		# Hack to print, irrespective of the log level
		self.__log(0, "List of IPs on the VMs")
		self.__log(0, self.all_ips)
		self.__log(INFO, "Shutdown the VMs after use")

		return self.all_ips

	def build_new(config_file):
		# If you have an existing object, and want to reinitialize it.
		self.__log(INFO, "Reconfiguring parameters from config file")
		self.__init__(config_file)

if __name__ == "__main__":
	if len(sys.argv) > 1:
		config_file = sys.argv[1]
	else:
		print("Error")
		print("Usage:")
		print("python3 do_qemu.py <path_to_config_file>")
		exit()
	print("Using config file", config_file)

	my_qemu = auto_qemu(config_file)
	my_qemu.start_auto()
