from do_automate.globals import *
from do_automate.do_ssh import SSH

''' check module rdma_rxe
	add rdma link
	do check "rdma link show" and "rdma dev"
'''

class softROCE:
	def __init__(self, log_obj):
		self.my_username = ""
		self.my_password = ""
		self.my_ip = ""
		self.my_ssh = SSH()

		# Set up log stuff
		self.log_obj = log_obj

	def __log(self, log_level, *args):
		message = self.__class__.__name__ + ": "
		for arg in args:
			message += str(arg) + " "

		self.log_obj.log(log_level, message)

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

	def __check_rdma_link(self, rdma_dev_name):
		# check whether link was added successfully
		self.__log(INFO, "confirming the addition of link..")
		status, status_string = self.__run_sudo_command_remote("rdma link show | grep {rdma_device}".format(rdma_device = rdma_dev_name))
		if not status or "LINK_UP" not in status_string[0]:
			self.__log(ERROR, status_string)
			return False

		self.__log(DEBUG, "RDMA link with link name {name} added to IP {ip}".format(name = rdma_dev_name, ip = self.my_ip))
		return True

	def __add_rdma_link_rxe(self, netdev, rdma_dev_name):
		self.__log(DEBUG, "In arlr", self.my_ip, self.my_username, self.my_password)
		command = "rxe_cfg add {netdev}".format(netdev = netdev)
		self.__log(DEBUG, command)
		status, status_string = self.__run_sudo_command_remote(command)
		rdma_dev_name = netdev
		if not status:
			return False

		return self.__check_rdma_link(rdma_dev_name)

	def __add_rdma_link(self, rdma_dev_name):
		self.__log(DEBUG, "In arl", self.my_ip, self.my_username, self.my_password)

		# get the interface name, since "rdma" commands uses names and not IPs
		self.__log(INFO, "Getting the network device name corresponding to the IP..")
		command = "ip -o -4 a | grep {ip} | awk '{{print $2}}'".format(ip = self.my_ip)
		self.__log(DEBUG, command)
		status, status_string = self.__run_command_remote(command)
		if not status:
			self.__log(ERROR, status_string)
			return False
		netdev = status_string[0]
		self.__log(INFO, "Done!")
		self.__log(DEBUG, "IP {ip} belongs to network device {netdev}".format(ip = self.my_ip, netdev = netdev))

		# Try adding the softROCE RDMA link
		self.__log(INFO, "Adding RDMA link..")
		command = "rdma link add {name} type {type} netdev {netdev}".format(name = rdma_dev_name, type = "rxe", netdev = netdev)
		self.__log(DEBUG, command)
		status, status_string = self.__run_sudo_command_remote(command)
		if not status:
			if "Invalid argument" in status_string[0]:
				# May be the older command might work
				return self.__add_rdma_link_rxe(netdev, rdma_dev_name)
			else:
				return False
		self.__log(INFO, "Done!")

		if not self.__check_rdma_link(rdma_dev_name):
			return self.__add_rdma_link_rxe(netdev, rdma_dev_name)

		return True

	def setup_softroce(self, ssh_username, ssh_password, ssh_ip, rdma_dev_name):
		self.my_username = ssh_username
		self.my_password = ssh_password
		self.my_ip = ssh_ip

		if not self.__check_insert_module():
			self.__log(ERROR, "Failure: insert module")
			return False

		if not self.__add_rdma_link(rdma_dev_name):
			self.__log(ERROR, "Failure: add RDMA link")
			return False

		self.__log(0, "All set. use ip {ip} as an rdma link with link name {name}".format(ip = self.my_ip, name = rdma_dev_name))
		return True

if __name__ == "__main__":
	print("Do not call me directly, I am an introvert!")
