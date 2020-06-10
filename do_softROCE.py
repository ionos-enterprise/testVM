import sys
from datetime import datetime

from do_ssh import SSH

''' check module rdma_rxe
	add rdma link
	do check "rdma link show" and "rdma dev"
'''

ERROR = 1
INFO = 2
DEBUG = 3

class softROCE:
	def __init__(self, log_file, log_level):
		self.my_username = ""
		self.my_password = ""
		self.my_ip = ""
		self.my_ssh = SSH()

		# Set up log stuff
		self.local_log_file = log_file
		self.log_level = log_level

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

	def __run_command_remote(self, command):
		return self.my_ssh.run_command(self.my_username, self.my_password, self.my_ip, command)

	def __run_sudo_command_remote(self, command):
		return self.my_ssh.run_sudo_command(self.my_username, self.my_password, self.my_ip, command)

	def __check_insert_module(self):
		self.__log(DEBUG, "In cim", self.my_ip, self.my_username, self.my_password)
		self.__log(INFO, "Checking and adding module rdma_rxe..")

		status, status_string = self.__run_sudo_command_remote("modprobe rdma_rxe")
		if not status:
			self.__log(ERROR, status_string)
			return False

		# Check once that the module exists
		status, status_string = self.__run_sudo_command_remote("lsmod | grep rdma_rxe")
		if not status:
			self.__log(ERROR, status_string)
			return False

		self.__log(INFO, "Done!\n")
		return True

	def __add_rdma_link(self):
		self.__log(DEBUG, "In arl", self.my_ip, self.my_username, self.my_password)
		self.__log(INFO, "Adding RDMA link")

		# get the interface name, since "rdma" commands uses names and not IPs
		self.__log(INFO, "Getting the network device name corresponding to the IP..")
		command = "netstat -ie | grep -B1 {ip} | head -n1 | awk '{{print $1}}'".format(ip = self.my_ip)
		self.__log(DEBUG, command)
		status, status_string = self.__run_command_remote(command)
		if not status:
			self.__log(ERROR, status_string)
			return False
		netdev = status_string[0][:-2]
		self.__log(INFO, "Done!")
		self.__log(DEBUG, "IP {ip} belongs to network device {netdev}".format(ip = self.my_ip, netdev = netdev))

		# Try adding the softROCE RDMA link
		self.__log(INFO, "Adding RDMA link..")
		command = "rdma link add {name} type {type} netdev {netdev}".format(name = "rdma_1", type = "rxe", netdev = netdev)
		self.__log(DEBUG, command)
		status, status_string = self.__run_sudo_command_remote(command)
		if not status:
			self.__log(ERROR, status_string)
			return False
		self.__log(INFO, "Done!")

		# check whether link was added successfully
		self.__log(INFO, "confirming the addition of link..")
		status, status_string = self.__run_sudo_command_remote("rdma link show")
		if not status:
			self.__log(ERROR, status_string)
			return False
		if "rdma_1" not in status_string[0] and "LINK_UP" not in status_string[0]:
			return False
		self.__log(DEBUG, "RDMA link with link name rdma_1 added to IP {ip}".format(ip = self.my_ip))

		self.__log(INFO, "Done!\n")
		return True

	def setup_softroce(self, ssh_username, ssh_password, ssh_ip):
		self.my_username = ssh_username
		self.my_password = ssh_password
		self.my_ip = ssh_ip

		# skipping module insertion since all modules are baked into bzImage
		'''
		if not self.__check_insert_module():
			self.__log(ERROR, "Failure: insert module")
			return False
		'''

		if not self.__add_rdma_link():
			self.__log(ERROR, "Failure: add RDMA link")
			return False

		self.__log(0, "All set. use ip {ip} as an rdma link with link name rdma_1".format(ip = self.my_ip))
		return True

if __name__ == "__main__":
	print("Do not call me directly, I am an introvert!")
