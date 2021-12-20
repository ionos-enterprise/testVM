#!/usr/bin/python3

from os import getcwd,environ
from os.path import expanduser,isdir
from datetime import datetime

DEFAULT_DATA_FOLDER_NAME = "do_automate_data"

# Get current directory path
current_directory = getcwd()

# Get path to default data folder
if (environ.get('DO_AUTOMATE_DATA')):
	default_data_path = environ.get('DO_AUTOMATE_DATA')
	if not isdir(default_data_path):
		print("Data path {path} does not exist".format(path = default_data_path))
		raise SystemExit
else:
	default_data_path = expanduser("~")

default_data_path = default_data_path + "/" + DEFAULT_DATA_FOLDER_NAME + "/"

# For persistent VMs
IMGS_FODLER = default_data_path + "/vm_imgs/"

# Path defaults
PIPES_FOLDER = default_data_path + "/vm_pipes/"

# Log related
ERROR = 1
INFO = 2
DEBUG = 3

log_dict = {
  "ERROR": 1,
  "INFO": 2,
  "DEBUG": 3
}

# CONST
NUM_OF_ETH_INT = 2

# Dynamic delay multiplier, used for heavy/slow VMs
vm_comm_delay_mult = 1

class do_automate_log:
	def __init__(self, log_file, log_level):
		# Set up log stuff
		self.local_log_file = log_file
		self.log_level = log_level

	def log(self, log_level, log_str):
		# Limit logging to 2000 characters
		log_str = ("..." + log_str[-2000:]) if len(log_str) > 2000 else log_str

		# Write to console
		if self.log_level >= log_level:
			print(log_str)

		# Write to log file
		log_str = datetime.now().strftime('%Y-%m-%d\t%H:%M:%S\t').expandtabs(4) + log_str
		log_str += "\n"
		with open(self.local_log_file, 'a') as log_file:
			log_file.write(log_str)



if __name__ == "__main__":
        print("Do not call me directly, I am an introvert!")
