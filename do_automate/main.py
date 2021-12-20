#!/usr/bin/python3

import sys
import json
import subprocess
import os.path
from datetime import datetime
from getpass import getpass
from argparse import ArgumentParser, SUPPRESS, RawTextHelpFormatter


from do_automate.globals import *
from do_automate.util import *
from do_automate.do_qemu import auto_qemu
from do_automate.vm_classes import da_vm_class
#from do_automate.vm_classes import server

# Globals
LOCAL_LOG_FOLDER = default_data_path + "/logs/"

build_options = ["all", "kernel", "module", "run"]

# Const
LINUX_KERNEL_FOLDER = default_data_path + "/linux/"
VM_SHARE_FOLDER = default_data_path + "/vm_share/"

# This is only used when VMs are spin up from this main file
SHARED_9P_TAG = "host0"

def run_command_local(command):
	try:
		s = subprocess.check_output([command], stderr=subprocess.DEVNULL, shell=True).decode('utf-8')
		returncode = 0
	except subprocess.CalledProcessError as e:
		s = e.output
		returncode = e.returncode
	# failure returns a positive returncode
	# success return 0 as returncode
	return returncode, s

def get_host_password(log_obj):
	ret, s = run_command_local("sudo -n true")
	if ret:
		log_obj.log(0, 'Enter host password')
		host_password = getpass()
	else:
		host_password = ""
	return host_password

def define_args():
	parser = ArgumentParser(add_help=False, formatter_class=RawTextHelpFormatter)
	req_arg = parser.add_argument_group('main arguments')
	opt_arg = parser.add_argument_group('optional arguments')

	# If config file is to be used
	req_arg.add_argument("-f", "--config-file", help="path to json config file\n")

	# Choose what to build
	req_arg.add_argument("-b", "--build", help="Choose what to build.\n"
					"Options: all - build kernel, modules, spin up VMs\n"
						 "kernel - build kernel, spin up VMs\n"
						 "module - build modules, spin up VMs\n"
						 "run - build nothing, spin up VMs\n")

	req_arg.add_argument("-s", "--show", nargs='?', const="default", help="print details of the running VMs\n")

	req_arg.add_argument("-C", "--command", nargs='*',
				help="send a command to VM. Option: shutdown, reboot.\n"
				"Example: ./do_qemu -C reboot 192.168.22.1,192.168.22.2..\n")

	req_arg.add_argument("-u", "--username", help="username of the VM\n")
	req_arg.add_argument("-p", "--password", help="password of the VM\n")

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

	if args.config_file:
		return args

	# Default to INFO log_level
	args.log_level = "INFO"

	# Default to root user if username not provided
	# This will mostly happen when the login is expected to happen through ssh key
	if not args.username:
		args.username = "root"

	if not args.password:
		args.password = "root"

	return args

def check_and_set_def_values(config_dict):
	# Default to root user if username not provided
	# This will mostly happen when the login is expected to happen through ssh key
	if not config_dict['username']:
		config_dict['username'] = "root"

	# if not set then use snapshot mode as default
	if "mode" not in config_dict.keys():
		print("mode parameter is not set in config, use \"snapshot\" by default")
		config_dict["mode"] = "snapshot"
	elif config_dict["mode"] not in ["snapshot", "persistent"]:
			print("Wrong mode {}, the possible values are \"snapshot\" or \"persistent\"".format(config_dict["mode"]))
			raise SystemExit

	return

def parse_config_file(config_file):
	try:
		with open(config_file) as json_file:
			config = json.load(json_file)

		server_class = config["server"]
		storage_class = config["storage"]
	except:
		return None, None

	server_dict = config[server_class["vm_class"]]
	storage_dict = config[storage_class["vm_class"]]

	server_dict["num_of_vm"] = server_class["num_of_vm"]
	storage_dict["num_of_vm"] = storage_class["num_of_vm"]

	server_dict["type"] = "server"
	storage_dict["type"] = "storage"

	check_and_set_def_values(server_dict)
	check_and_set_def_values(storage_dict)

	return server_dict, storage_dict

def create_log_folder():
	command = "mkdir -p {folder}".format(folder = LOCAL_LOG_FOLDER)
	try:
		s = subprocess.check_output([command], stderr=subprocess.DEVNULL, shell=True).decode('utf-8')
		returncode = 0
	except subprocess.CalledProcessError as e:
		print("create_log_folder() failed!")
		return False

	return True

def create_pipes_folder():
	command = "mkdir -p {folder}".format(folder = PIPES_FOLDER)
	try:
		s = subprocess.check_output([command], stderr=subprocess.DEVNULL, shell=True).decode('utf-8')
		returncode = 0
	except subprocess.CalledProcessError as e:
		print("create_pipes_folder() failed!")
		return False

	return True

def create_monitor_folder():
	command = "mkdir -p {folder}".format(folder = default_data_path + "vm_monitors/")
	try:
		s = subprocess.check_output([command], stderr=subprocess.DEVNULL, shell=True).decode('utf-8')
		returncode = 0
	except subprocess.CalledProcessError as e:
		print("create_monitor_folder() failed!")
		return False

	return True

def create_img_folder():
	command = "mkdir -p {folder}".format(folder=IMGS_FODLER)
	try:
		s = subprocess.check_output([command], stderr=subprocess.DEVNULL, shell=True).decode('utf-8')
		returncode = 0
	except subprocess.CalledProcessError as e:
		print("create_img_folder() failed!")
		return False

	return True

def create_log_object(log_level):
	# Create the log file
	log_file = LOCAL_LOG_FOLDER + "log_" + datetime.now().strftime('%Y-%m-%d_%H:%M:%S')

	# This log level is only for console.
	# In the file, everything gets logged. EVERYTHING!
	if log_level not in log_dict.keys():
		log_level = "INFO"
		print("Unknown Log level")
		print("Setting log level to INFO by default")
	log_level = log_dict[log_level]

	# Create log object for this session
	log_obj = do_automate_log(log_file, log_level)
	print("Log file ", log_file)

	return log_obj

def create_log_obj_from_config_file(config_file):
	try:
		with open(config_file) as json_file:
			config = json.load(json_file)

		log_level = config["log_level"]
	except:
		print("Error reading log level from config file")
		print("Setting log level to INFO by default")
		log_level = "INFO"

	log_obj = create_log_object(log_level)

	return log_obj

def check_build_options(args):
	if not args.build:
		args.build = "all"

	if args.build not in build_options:
		return False

	return True

def main():
	parser = define_args()

	if len(sys.argv) == 1:
		parser.print_help(sys.stderr)
		raise SystemExit

	# Create log folder if not present
	if not create_log_folder():
		print("Creating log folders failed")
		raise SystemExit

	# Create pipes folder if not present
	if not create_pipes_folder():
		print("Creating pipes folders failed")
		raise SystemExit

	# Create folder for monitor unix sockets if not present
	if not create_monitor_folder():
		print("Creating monitor folder failed")
		raise SystemExit

	if not create_img_folder():
		print("Create img copy folders failed")
		raise SystemExit

	args = parse_arguments(parser)

	if args.config_file:
		# We have a config file

		# Create log object
		log_obj = create_log_obj_from_config_file(args.config_file)
		if not log_obj:
			print("Error creating log object")
			raise SystemExit

		server_dict, storage_dict = parse_config_file(args.config_file)
		if not server_dict:
			log_obj.log(ERROR, "Error parsing config file")
			raise SystemExit

		if int(server_dict['num_of_vm']) <= 0 and int(storage_dict['num_of_vm']) <= 0:
			log_obj.log(0, "No VM to spin up")
			raise SystemExit

		if not check_build_options(args):
			log_obj.log(0, "Unknown build option")
			raise SystemExit

		# If sudo requires password, ask for it
		host_password = get_host_password(log_obj)

		server_ips = ""
		storage_ips = ""

		my_vm_obj = da_vm_class(log_obj)

		if int(server_dict['num_of_vm']) > 0:
			# Start server VM
			if not my_vm_obj.set_vm_params(server_dict, args.build):
				log_obj.log(ERROR, "set_vm_params() for server failed")
				raise SystemExit
			ret = my_vm_obj.start_auto(host_password)
			if not ret:
				log_obj.log(ERROR, "Server VM Init failed")
				raise SystemExit
			server_ips = ret

		if int(storage_dict['num_of_vm']) > 0:
			# Start storage VM
			if not my_vm_obj.set_vm_params(storage_dict, args.build):
				log_obj.log(ERROR, "set_vm_params() for storage failed")
				raise SystemExit
			ret = my_vm_obj.start_auto(host_password)
			if not ret:
				log_obj.log(ERROR, "Storage VM Init failed")
				raise SystemExit
			storage_ips = ret

		if server_ips:
			log_obj.log(0, "Server VM IPs: {ips}".format(ips = server_ips))
		if storage_ips:
			log_obj.log(0, "Storage VM IPs: {ips}".format(ips = storage_ips))

		# Done
		raise SystemExit

	log_obj = create_log_object(args.log_level)
	if not log_obj:
		print("Error creating log object")
		raise SystemExit

	if args.show:
		dac_obj = da_command(log_obj)
		dau_obj = da_util(log_obj, dac_obj)

		if args.show == "ip":
			dau_obj.print_running_vm_ips()
		else:
			dau_obj.print_running_vm_details()

		raise SystemExit

	if args.command is not None:
		# Just sending commands to already running VMs

		my_vm_obj = da_vm_class(log_obj)
		command = args.command[0]
		if command == "shutdown":
			my_func = my_vm_obj.shutdown_vm
		elif command == "reboot":
			my_func = my_vm_obj.reboot_vm
		else:
			log_obj.log(0, "Unknown command {comm}".format(comm = command))
			raise SystemExit

		# If sudo requires password, ask for it
		# Needed when IP is down and pipe console is to be used
		host_password = get_host_password(log_obj)

		vm_ips = args.command[1].split(",")
		for ip in vm_ips:
			if not my_func(ip, args.username, args.password, host_password):
				log_obj.log(ERROR, "{function} failed for ip {ip}".format(function = my_func.__name__, ip = ip))
		raise SystemExit

	log_obj.log(ERROR, "Nothing to do.")

if __name__ == "__main__":
	main()
