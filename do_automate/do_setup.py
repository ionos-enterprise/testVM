#!/usr/bin/python3

import os
import subprocess
from argparse import ArgumentParser, SUPPRESS, RawTextHelpFormatter

default_path = "/tmp/"
BRIDGE_2_NAME = "bridge_2"

# Get current directory path
current_directory = os.getcwd()

def define_args():
	parser = ArgumentParser(add_help=False, formatter_class=RawTextHelpFormatter)
	opt_arg = parser.add_argument_group('optional arguments')

	opt_arg.add_argument("-b", "--bridge", help="Check and setup only bridges\n", action='store_true')
	opt_arg.add_argument("-i", "--image", help="Generate an debian image file to use with do_qemu\n", action='store_true')

	opt_arg.add_argument(
		'-h',
		'--help',
		action='help',
		default=SUPPRESS,
		help='show this help message and exit\n'
	)

	return parser

def parse_arguments(parser):
	args = parser.parse_args()

	return args

class do_setup:
	def __init__(self):
		pass

	def __log(self, *args):
		message = self.__class__.__name__ + ": "
		for arg in args:
			message += str(arg) + " "

		print(message)

	def __run_command_local(self, command):
		self.__log(command)
		try:
			s = subprocess.check_output([command], stderr=subprocess.DEVNULL, shell=True).decode('utf-8')
			returncode = 0
		except subprocess.CalledProcessError as e:
			s = e.output
			returncode = e.returncode
		self.__log(returncode, s)
                # failure returns a positive returncode
                # success return 0 as returncode
		return returncode, s

	def __get_user_resp(self, task):
		yes = ["yes", "ye", "y", ""]
		no = ["no", "n"]
		skip = ["skip", "ski", "sk", "s"]
		self.__log("About to perform the following task")
		self.__log(task)

		while True:
			ch = input("Continue (yes/no/skip): ").lower()
			if ch in yes:
				return True
			elif ch in skip:
				return False
			elif ch in no:
				self.__log("Exiting!")
				raise SystemExit
			else:
				self.__log("Please enter a valid choice!")

	def __generate_rand_char(self, except_this):
		char = chr(ord(except_this) + 1)
		if char == 'g' or char == ':':
			# lucky number
			char = '8'
		return char

	def __check_start_bridge(self, my_bridge):
		command = "virsh net-info {bridge} | grep Active | awk '{{print $2}}'".format(bridge = my_bridge)
		status, status_string = self.__run_command_local(command)
		if status:
			self.__log("Fail! ", status_string)
			return False

		if status_string.rstrip() == "yes":
			return True

		return False

	def __check_autostart_bridge(self, my_bridge):
		command = "virsh net-info {bridge} | grep Autostart | awk '{{print $2}}'".format(bridge = my_bridge)
		status, status_string = self.__run_command_local(command)
		if status:
			self.__log("Fail! ", status_string)
			return False

		if status_string.rstrip() == "yes":
			return True

		return False

	def __start_bridge(self, my_bridge):
		if self.__check_start_bridge(my_bridge):
			self.__log("Bridge {bridge} already activated\n".format(bridge = my_bridge))
			return True

		command = "virsh net-start {bridge}".format(bridge = my_bridge)
		status, status_string = self.__run_command_local(command)

		# Check once more
		if self.__check_start_bridge(my_bridge):
			self.__log("Bridge {bridge} activated\n".format(bridge = my_bridge))
			return True

		return False

	def __autostart_bridge(self, my_bridge):
		if self.__check_autostart_bridge(my_bridge):
			self.__log("Bridge {bridge} already set to autostart\n".format(bridge = my_bridge))
			return True

		command = "virsh net-autostart {bridge}".format(bridge = my_bridge)
		status, status_string = self.__run_command_local(command)
		if status:
			self.__log("Fail! ", status_string)
			return False

		# Check once more
		if self.__check_autostart_bridge(my_bridge):
			self.__log("Bridge {bridge} set to autostart\n".format(bridge = my_bridge))
			return True

		return False

	def create_qcow_image(self):
		self.__log("Creating qcow image file.")
		command = "mktemp"
		status, status_string = self.__run_command_local(command)
		if status:
			self.__log("Fail! ", status_string)
			return False

		tmp_file = status_string.rstrip()
		command = "dd if=/dev/zero of={i_file} bs=1M count=4096".format(i_file = tmp_file)
		status, status_string = self.__run_command_local(command)
		if status:
			self.__log("Fail! ", status_string)
			return False

		command = "losetup -fP {i_file}".format(i_file = tmp_file)
		status, status_string = self.__run_command_local(command)
		if status:
			self.__log("Fail! ", status_string)
			return False

		command = "losetup | grep {i_file} | awk '{{print $1}}'".format(i_file = tmp_file)
		status, status_string = self.__run_command_local(command)
		if status:
			self.__log("Fail! ", status_string)
			return False

		loop_dev = status_string.rstrip()
		command = "parted {loop_d} mklabel gpt mkpart primary ext4 2048 100%".format(loop_d = loop_dev)
		status, status_string = self.__run_command_local(command)
		if status:
			self.__log("Fail! ", status_string)
			return False

		command = "mkfs.ext4 {loop_d}p1".format(loop_d = loop_dev)
		status, status_string = self.__run_command_local(command)
		if status:
			self.__log("Fail! ", status_string)
			return False

		command = "mktemp -d"
		status, status_string = self.__run_command_local(command)
		if status:
			self.__log("Fail! ", status_string)
			return False

		mount_point = status_string.rstrip()
		command = "mount {loop_d}p1 {mount_p}".format(loop_d = loop_dev, mount_p = mount_point)
		status, status_string = self.__run_command_local(command)
		if status:
			self.__log("Fail! ", status_string)
			return False

		command = "debootstrap --include=iproute2,network-manager,openssh-server,sudo,infiniband-diags,rdma-core,psmisc,ibverbs-utils,ethtool stable {mount_p} http://deb.debian.org/debian/".format(mount_p = mount_point)
		status, status_string = self.__run_command_local(command)
		if status:
			self.__log("Fail! ", status_string)
			return False

		command = "mkdir -p {mount_p}/lib/modules".format(mount_p = mount_point)
		status, status_string = self.__run_command_local(command)
		if status:
			self.__log("Fail! ", status_string)
			return False

		command = "sed -i 's/^\(.\|\)PermitRootLogin.*/PermitRootLogin yes/g' {mount_p}/etc/ssh/sshd_config".format(mount_p = mount_point)
		status, status_string = self.__run_command_local(command)
		if status:
			self.__log("Fail! ", status_string)
			return False

		command = "openssl passwd -1 root"
		status, status_string = self.__run_command_local(command)
		if status:
			self.__log("Fail! ", status_string)
			return False

		root_password = status_string.rstrip()
		command = "sed -i 's|^root:x|root:{root_p}|g' {mount_p}/etc/passwd".format(root_p = root_password, mount_p = mount_point)
		status, status_string = self.__run_command_local(command)
		if status:
			self.__log("Fail! ", status_string)
			return False

		command = "sed -i 's|^root:x|root:{root_p}|g' {mount_p}/etc/passwd-".format(root_p = root_password, mount_p = mount_point)
		status, status_string = self.__run_command_local(command)
		if status:
			self.__log("Fail! ", status_string)
			return False

		command = "umount {mount_p} && losetup -d {loop_d}".format(mount_p = mount_point, loop_d = loop_dev)
		status, status_string = self.__run_command_local(command)
		if status:
			self.__log("Fail! ", status_string)
			return False

		command = "qemu-img convert -f raw -O qcow2 {i_file} {path}/debian.qcow2".format(i_file = tmp_file, path = current_directory)
		status, status_string = self.__run_command_local(command)
		if status:
			self.__log("Fail! ", status_string)
			return False

		command = "rm -rf {mount_p} {i_file}".format(mount_p = mount_point, i_file = tmp_file)
		status, status_string = self.__run_command_local(command)
		if status:
			self.__log("Fail! ", status_string)
			return False

		self.__log("All done!")
		self.__log("The create debian image is {path}/debian.qcow2".format(path = current_directory))

		return True

	def install_packages(self):
		# For kernel make
		command = "apt install -y libncurses-dev flex bison openssl libssl-dev dkms libelf-dev libudev-dev libpci-dev libiberty-dev autoconf"

		if self.__get_user_resp(command):
			status, status_string = self.__run_command_local(command)
			if status:
				self.__log("Fail! ", status_string)
				return False
		else:
			self.__log("Skipped. Make sure those packages are installed\n")

		# For qemu
		command = "apt install -y qemu qemu-utils qemu-system qemu-kvm"

		if self.__get_user_resp(command):
			status, status_string = self.__run_command_local(command)
			if status:
				self.__log("Fail! ", status_string)
				return False
		else:
			self.__log("Skipped. Make sure those packages are installed\n")

		# For libvirt stuff
		command = "apt install -y libvirt-clients libvirt-daemon-system virtinst bridge-utils"

		if self.__get_user_resp(command):
			status, status_string = self.__run_command_local(command)
			if status:
				self.__log("Fail! ", status_string)
				return False
		else:
			self.__log("Skipped. Make sure those packages are installed\n")

		# Generic packages used
		command = "apt install -y net-tools dnsmasq"

		if self.__get_user_resp(command):
			status, status_string = self.__run_command_local(command)
			if status:
				self.__log("Fail! ", status_string)
				return False
		else:
			self.__log("Skipped. Make sure those packages are installed\n")

		return True

	def add_bridges_to_acl(self, all_bridges_name):
		if os.path.exists("/etc/qemu/bridge.conf"):
			command = "grep -w 'allow all' /etc/qemu/bridge.conf"
			status, status_string = self.__run_command_local(command)
			if status:
				for b_name in all_bridges_name:
					command = "grep -w 'allow " + b_name + "' /etc/qemu/bridge.conf"
					status, status_string = self.__run_command_local(command)
					if status and self.__get_user_resp("Bridge " + b_name + " not whitelisted. Add to whitelist?"):
						command = "echo 'allow " + b_name + "' >> /etc/qemu/bridge.conf"
						status, status_string = self.__run_command_local(command)
						if status:
							self.__log("Fail! ", status_string)
							return False
		else:
			if self.__get_user_resp("File /etc/qemu/bridge.conf does not exist. Create file and whitelist bridges?"):
				command = "mkdir -p /etc/qemu && touch /etc/qemu/bridge.conf"
				status, status_string = self.__run_command_local(command)
				if status:
					self.__log("Fail! ", status_string)
					return False
				for b_name in all_bridges_name:
					command = "echo 'allow " + b_name + "' >> /etc/qemu/bridge.conf"
					status, status_string = self.__run_command_local(command)
					if status:
						self.__log("Fail! ", status_string)
						return False
		return True

	def configure_bridge_1(self):
		# Default bridge not found. Something is wrong. Trying once still
		command = "virsh net-define /etc/libvirt/qemu/networks/default.xml"
		status, status_string = self.__run_command_local(command)

		if not self.__start_bridge("default") or not self.__autostart_bridge("default"):
			self.__log("Fail!")
			return False

		return True

	def configure_bridge_2(self):
		with open("/etc/libvirt/qemu/networks/default.xml") as f:
			bridge_file = f.readlines()

		for i in range(len(bridge_file)):
			line = bridge_file[i]
			if "<name>" in line:
				bridge_file[i] = "  <name>" + BRIDGE_2_NAME + "</name>\n"
			elif "<uuid>" in line:
				point = line.find("</uuid>") - 1
				char = self.__generate_rand_char(line[point])
				bridge_file[i] = line[:point] + str(char) + line[point+1:]
			elif "<bridge name=" in line:
				point = line.find("virbr") + 5
				bridge_file[i] = line[:point] + str(1) + line[point+1:]
			elif "<mac address=" in line:
				point = line.find("'/>") - 1
				char = self.__generate_rand_char(line[point])
				bridge_file[i] = line[:point] + str(char) + line[point+1:]
			elif "<ip address=" in line:
				point = line.find("netmask") - 5
				bridge_file[i] = line[:point] + str(3) + line[point+1:]
			elif "<range start=" in line:
				point = line.find("end") - 5
				bridge_file[i] = line[:point] + str(3) + line[point+1:]
				line = bridge_file[i]
				point = line.find("'/>") - 5
				bridge_file[i] = line[:point] + str(3) + line[point+1:]

		bridge_file_name = default_path + BRIDGE_2_NAME + ".xml"
		with open(bridge_file_name, "w+") as f:
			f.writelines(bridge_file)

		# create the bridge
		command = "virsh net-define " + bridge_file_name

		status, status_string = self.__run_command_local(command)
		if status:
			self.__log("Fail! ", status_string)
			# Do not fail here. Its possible that the network is defined but not started. Try to start
			# return False

		# Check and start + autostart the bridge
		if not self.__start_bridge(BRIDGE_2_NAME) or not self.__autostart_bridge(BRIDGE_2_NAME):
			self.__log("Fail!")
			return False

		return True

	def configure_bridges(self):
		command = "virsh net-list | awk 'NR>2'"
		status, status_string = self.__run_command_local(command)
		all_bridges_name = []
		all_bridges = list(filter(None, status_string.split("\n")))

		for bridge in all_bridges:
			this_bridge = list(filter(None, bridge.split(" ")))
			command = "virsh net-info " + this_bridge[0] + " | grep Bridge"
			status, status_string = self.__run_command_local(command)
			this_bridge_name = list(filter(None, status_string.split(" ")))[1].rstrip()
			if this_bridge[1] != "active":
				if self.__get_user_resp("Bridge " + this_bridge[0] + " named " + this_bridge_name + "not active. Start now?"):
					if not self.__start_bridge(this_bridge[0]):
						self.__log("Fail!")
						return False
			if this_bridge[2] != "yes":
				if self.__get_user_resp("Bridge " + this_bridge[0] + " named " + this_bridge_name + "not set to autostart. Set now?"):
					if not self.__autostart_bridge(this_bridge[0]):
						self.__log("Fail!")
						return False
			all_bridges_name.append(this_bridge_name)

		if len(all_bridges_name) >= 2:
			self.__log("You seem to have more than 1 virt bridge configured. Thats good.")
			self.__log("Use 2 of the below bridges for the VMs")
			self.__log(all_bridges_name, "\n")
		elif len(all_bridges_name) == 1:
			self.__log("You have 1 virt bridge configured, below mentioned")
			self.__log(all_bridges_name, "\n")
			if self.__get_user_resp("Configure second bridge?"):
				self.__log("Configuring bridge number 2")
				if not self.configure_bridge_2():
					self.__log("Fail! self.configure_bridge_2()")
					return False
				all_bridges_name.append("virbr1")
		else:
			self.__log("No configured bridge found. This is unexpected")
			if self.__get_user_resp("Do you want the script to try to configure both the bridges?"):
				self.__log("Configuring bridge number 1")
				if not self.configure_bridge_1():
					self.__log("Fail! self.configure_bridge_1()")
					return False
				self.__log("Configuring bridge number 2")
				if not self.configure_bridge_2():
					self.__log("Fail! self.configure_bridge_2()")
					return False
				all_bridges_name = ["virbr0", "virbr1"]

		if not self.add_bridges_to_acl(all_bridges_name):
			self.__log("Fail! self.add_bridges_to_acl()")
			return False

		return True

	def insert_modules(self):
		command = "modprobe kvm"

		status, status_string = self.__run_command_local(command)
		if status:
			self.__log("Fail! ", status_string)
			return False

		command = "modprobe kvm-intel && modprobe kvm-amd"
		status, status_string = self.__run_command_local(command)

		return True

	def start_setup(self):
		if not self.install_packages():
			self.__log("Installing packages failed!")
			return

		if not self.configure_bridges():
			self.__log("Configuring bridges failed!")
			return

		if not self.insert_modules():
			self.__log("Inserting modules failed!")
			return

		print("\nSetup successful")

def setup():
	parser = define_args()

	args = parse_arguments(parser)

	if os.geteuid():
		print("Please run as sudo")
		raise SystemExit

	setup_obj = do_setup()

	if args.bridge:
		if not setup_obj.configure_bridges():
			print("Configuring bridges failed!")
		raise SystemExit

	if args.image:
		if not setup_obj.create_qcow_image():
			print("Creation of debian image failed")
		raise SystemExit

	setup_obj.start_setup()

if __name__ == "__main__":
	setup()
