#!/usr/bin/python3

import subprocess
import sys
import time
import json
import errno
from os import kill
from pprint import pprint

from do_automate.globals import *
from do_automate.do_ssh import SSH

class da_command:
	def __init__(self, log_obj, username="", password="", host_password=""):
		self.log_obj = log_obj

		# For remote commands
		self.my_ssh = SSH()

		self.my_username = username
		self.my_password = password

		self.host_password = host_password

	def __log(self, log_level, *args):
		message = self.__class__.__name__ + ": "
		for arg in args:
			message += str(arg) + " "

		self.log_obj.log(log_level, message)

	def set_param(self, username=None, password=None, host_password=None):
		if username:
			self.my_username = username

		if password:
			self.my_password = password

		if host_password:
			self.host_password = host_password

	def run_command_remote(self, command, my_ip):
		self.__log(DEBUG, command, " @ remote: ", my_ip)
		try:
			status, status_string = self.my_ssh.run_command(self.my_username, self.my_password, my_ip, command)
		except:
			return 0, "Exception occurred: " + str(sys.exc_info()[0])
		self.__log(DEBUG, status, status_string)
		# failure returns 0 in status, stderr output in status_string
		return status, status_string

	def run_sudo_command_remote(self, command, my_ip):
		self.__log(DEBUG, "sudo ", command, " @ remote: ", my_ip)
		try:
			status, status_string =	self.my_ssh.run_sudo_command(self.my_username, self.my_password, my_ip, command)
		except:
			return 0, "Exception occurred: " + str(sys.exc_info()[0])
		self.__log(DEBUG, status, status_string)
		# failure returns 0 in status, stderr output in status_string
		return status, status_string

	def run_command_local(self, command):
		self.__log(DEBUG, command, " @ local")
		try:
			s = subprocess.check_output([command], stderr=subprocess.DEVNULL, shell=True).decode('utf-8')
			returncode = 0
		except subprocess.CalledProcessError as e:
			s = e.output
			returncode = e.returncode
		self.__log(DEBUG, returncode, s)
		# failure returns a positive returncode
		# success return 0 as returncode
		return returncode, s

	def run_sudo_command_local(self, command):
		self.__log(DEBUG, "__run_sudo_command_local(): sudo ", command, " @ local")
		command = "sudo -S " + command

		feed_password = subprocess.Popen("echo " + self.host_password, stdout=subprocess.PIPE, shell=True)
		status_string = subprocess.Popen(command, stdin=feed_password.stdout, stdout=subprocess.PIPE, shell=True)
		self.__log(DEBUG, status_string)

		return True

	def run_sudo_command_local_get_pid(self, command):
		self.__log(DEBUG, "__run_sudo_command_local(): sudo ", command, " @ local")
		command = "sudo -S " + command

		feed_password = subprocess.Popen("echo " + self.host_password, stdout=subprocess.PIPE, shell=True)
		status_string = subprocess.Popen(command, stdin=feed_password.stdout, stdout=subprocess.PIPE, shell=True).pid
		self.__log(DEBUG, status_string)

		return status_string

	def run_sudo_command_local_ret_out(self, command):
		self.__log(DEBUG, "__run_sudo_command_local_ret_out(): sudo ", command, " @ local")
		command = "sudo {comm}".format(comm = command)

		feed_password = subprocess.Popen("echo " + self.host_password, stdout=subprocess.PIPE, shell=True)
		status_string = subprocess.Popen(command, stdin=feed_password.stdout, stdout=subprocess.PIPE, shell=True)

		# Get the output from stdout
		status_string = status_string.stdout.read().decode()
		self.__log(DEBUG, "status_string ", status_string)

		return status_string

	def run_command_remote_pipe(self, uuid, rem_command, timeout):
		if not self.pipe:
			self.__log(ERROR, "__run_command_remote_pipe: Pipe not active.")
			return False

		global vm_comm_delay_mult

		self.__log(DEBUG, rem_command, " @ local using pipe")
		this_pipe_in = PIPES_FOLDER + "/" + uuid + ".in"
		this_pipe_out = PIPES_FOLDER + "/" + uuid + ".out"

		# Flush any stdout content before using
		command = "timeout 2 cat {pipe}".format(pipe = this_pipe_out)
		status_string = self.__run_sudo_command_local_ret_out(command)

		rem_command = rem_command + "\n"
		try:
			with open(this_pipe_in, 'w') as f:
				f.write(rem_command)
		except:
			self.__log(DEBUG, "__run_command_remote_pipe Failed with Exception: " + str(sys.exc_info()[0]))
			return 0, "Failure"

		command = "timeout {t_val} cat {pipe}".format(t_val = timeout * vm_comm_delay_mult, pipe = this_pipe_out)
		status_string = self.__run_sudo_command_local_ret_out(command)
		if not status_string:
			self.__log(DEBUG, "__run_sudo_command_local_ret_out Failed:", status_string)
			return 0, status_string

		# Remove the first line which contains the command,
		# and the last one which will contain the prompt
		status_string = "\n".join(status_string.split('\n')[1:-1])

		# failure returns 0 in status, stderr output in status_string
		return 1, status_string

	def run_sudo_command_remote_pipe(self, uuid, rem_command, timeout):
		if not self.pipe:
			self.__log(ERROR, "__run_sudo_command_remote_pipe: Pipe not active.")
			return False

		global vm_comm_delay_mult

		self.__log(DEBUG, "sudo ", rem_command, " @ local using pipe")
		this_pipe_in = PIPES_FOLDER + "/" + uuid + ".in"
		this_pipe_out = PIPES_FOLDER + "/" + uuid + ".out"

		# Flush any stdout content before using
		command = "timeout 2 cat {pipe}".format(pipe = this_pipe_out)
		status_string = self.__run_sudo_command_local_ret_out(command)

		command = "sudo " + rem_command + "\n"
		try:
			with open(this_pipe_in, 'w') as f:
				f.write(command)
		except:
			self.__log(DEBUG, "__run_sudo_command_remote_pipe Failed with Exception: " + str(sys.exc_info()[0]))
			return 0, "Failure"

		time.sleep(1 * vm_comm_delay_mult)
		command = "{password}\n".format(password = self.my_password)
		try:
			with open(this_pipe_in, 'w') as f:
				f.write(command)
		except:
			self.__log(DEBUG, "__run_sudo_command_remote_pipe Failed with Exception: " + str(sys.exc_info()[0]))
			return 0, "Failure"

		command = "timeout {t_val} cat {pipe}".format(t_val = timeout * vm_comm_delay_mult, pipe = this_pipe_out)
		status_string = self.__run_sudo_command_local_ret_out(command)
		if not status_string:
			self.__log(DEBUG, "__run_sudo_command_local_ret_out Failed:", status_string)
			return 0, status_string

		# Remove the first line which contains the command,
		# and the last one which will contain the prompt
		status_string = "\n".join(status_string.split('\n')[1:-1])

		# failure returns 0 in status, stderr output in status_string
		return 1, status_string

class da_get:
	def __init__(self, log_obj, dac_object):
		self.log_obj = log_obj
		self.dac_obj = dac_object

	def __log(self, log_level, *args):
		message = self.__class__.__name__ + ": "
		for arg in args:
			message += str(arg) + " "

		self.log_obj.log(log_level, message)

	def read_vm_details_json(self):
		vm_details_dict = {}
		vm_details_json_file = default_data_path + "/vm_details.json"
		try:
			with open(vm_details_json_file) as json_file:
				vm_details_dict = json.load(json_file)
		except FileNotFoundError:
			self.__log(DEBUG, "read_vm_details_json(): File not found, using new empty dict")
			vm_details_dict = {}
		except:
			self.__log(ERROR, "read_vm_details_json(): Exception occurred: " + str(sys.exc_info()[0]))
			return None

		return vm_details_dict

	def get_ip_from_mac(self, my_mac_addr):
		global vm_comm_delay_mult

		command = "arp -n"
		ip_attempts = 0
		while ip_attempts < 500:
			self.__log(DEBUG, "Attempt", ip_attempts + 1)
			status, s = self.dac_obj.run_command_local(command)
			if status:
				return None
			lines_list = s.split("\n")

			for line in lines_list:
				if my_mac_addr in line:
					delay_mult = int(ip_attempts / 5) + 1
					if vm_comm_delay_mult < delay_mult:
						vm_comm_delay_mult = delay_mult
					return line[:line.index(" ")]
			ip_attempts += 1
			self.__log(DEBUG, "Failed! Waiting 1 seconds before next try\n")
			time.sleep(1)
		return None

	def get_dev_name_from_ip(self, my_ip):
		command = "ip -o -4 a | grep '{ip}' | awk '{{print $2}}'".format(ip = my_ip)
		status, status_string = self.dac_obj.run_command_remote(command, my_ip)
		if (not status) or isinstance(status_string, (int, float)):
			# when status_string is bool and not list, that means the command did not find a match
			self.__log(ERROR, status_string)
			return False
		return status_string[0].rstrip()

	def get_uuid_from_ip(self, my_ip):
		vm_dict = self.read_vm_details_json()
		if vm_dict is None:
			self.__log(ERROR, "read_vm_details_json() failed: ", vm_dict)
			return False

		for uuid, vm_details_list in vm_dict.items():
			if my_ip in vm_details_list["ip"]:
				return uuid

		return None

	def get_mac_of_all_interfaces(self, my_ip):
		command = "ip -o -0 a | grep 'ens.' | awk '{{print $15}}'".format(ip = my_ip)
		status, status_string = self.dac_obj.run_command_remote(command, my_ip)
		if (not status) or isinstance(status_string, (int, float)):
			# when status_string is bool and not list, that means the command did not find a match
			self.__log(ERROR, status_string)
			return False
		return list(map(str.strip, status_string))

class da_util:
	def __init__(self, log_obj, dac_object):
		self.log_obj = log_obj
		self.dac_obj = dac_object

		self.dag_obj = da_get(self.log_obj, self.dac_obj)

	def __log(self, log_level, *args):
		message = self.__class__.__name__ + ": "
		for arg in args:
			message += str(arg) + " "

		self.log_obj.log(log_level, message)

	def ping_check(self, ping_attempts, my_ip, my_interval=1):
		command = "ping -c 1 -i {interval} {ip}".format(ip = my_ip, interval = my_interval)
		my_attempts = 0
		while my_attempts < ping_attempts:
			self.__log(DEBUG, "Attempt", my_attempts + 1)
			status, s = self.dac_obj.run_command_local(command)
			if not status:
				return True
			my_attempts += 1
			self.__log(DEBUG, "Failed! Waiting 2 seconds before next try\n")
			time.sleep(2)
		return False

	def is_vm_running(self, vm_details_list):
		try:
			kill(vm_details_list["pid"], 0)
		except OSError as err:
			if err.errno == errno.ESRCH:
				# VM process not running
				return False, False
			elif err.errno == errno.EPERM:
				# VM running, but we do not have permission to send signal
				# check network
				if not self.ping_check(1, vm_details_list['ips'][0], 0.2):
					# Network down
					return True, False

		# First is for process, second is network connectivity
		return True, True

	def is_path_absolute(self, path):
		if path[0] == '/' or path[0] == '~':
			return True
		return False

	def check_and_make_path_abs(self, path):
		if self.is_path_absolute(path):
			return path
		else:
			return current_directory + "/" + path

	def save_vm_details_to_json(self, vm_details_dict):
		vm_details_json_file = default_data_path + "/vm_details.json"
		try:
			with open(vm_details_json_file, 'w+') as json_file:
				json.dump(vm_details_dict, json_file, indent=8)
		except:
			self.__log(ERROR, "save_vm_details_to_json(): Exception occurred: " + str(sys.exc_info()[0]))
			return False

		return True

	def read_and_update_vm_dict(self):
		vm_dict = self.dag_obj.read_vm_details_json()
		if vm_dict is None:
			self.__log(ERROR, "read_vm_details_json() failed: ", vm_dict)
			return False

		temp_dict = vm_dict.copy()
		for uuid, vm_details_list in temp_dict.items():
			# Update the dict by checking if the vms are running
			vm_proc, vm_net = self.is_vm_running(vm_details_list)
			if not vm_proc:
				self.__log(DEBUG, "read_and_update_vm_dict(): VM {this_uuid} not found".format(this_uuid = uuid))
				del vm_dict[uuid]
				# Also delete the pipe files
				if "pipe" in vm_details_list["optional"]:
					if not self.__delete_pipe_files(uuid):
						self.__log(DEBUG, "save_vm_details_to_json Failed")
						return False
			elif not vm_net:
				vm_dict[uuid]["state"] = "Network Down (Maybe)"
			else:
				self.__log(DEBUG, "read_and_update_vm_dict(): VM {this_uuid} found running".format(this_uuid = uuid))

		if not self.save_vm_details_to_json(vm_dict):
			self.__log(DEBUG, "save_vm_details_to_json Failed")
			return False

		return vm_dict

	def print_running_vm_details(self):
		vm_dict = self.read_and_update_vm_dict()
		if vm_dict is False:
			self.__log(ERROR, "__print_running_vm_details(): read_and_update_vm_dict Failed")
			return False

		pprint(vm_dict)

	def print_running_vm_ips(self):
		vm_dict = self.read_and_update_vm_dict()
		if vm_dict is False:
			self.__log(ERROR, "__print_running_vm_details(): read_and_update_vm_dict Failed")
			return False

		for vm_details in vm_dict.values():
			print("{name}\t{ip1}\t{ip2}".format(name=vm_details["vm_name"],ip1=vm_details["ips"][0],ip2=vm_details["ips"][1]))
