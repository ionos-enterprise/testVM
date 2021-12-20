# Taken from https://gist.github.com/vladwa/bc49621782736a825844ee4c2a7dacae
# Changes added

import paramiko

class SSH:
	def __init__(self):
		pass

	def get_ssh_connection(self, ssh_machine, ssh_username, ssh_password):
		"""Establishes a ssh connection to execute command.
		:param ssh_machine: IP of the machine to which SSH connection to be established.
		:param ssh_username: User Name of the machine to which SSH connection to be established..
		:param ssh_password: Password of the machine to which SSH connection to be established..
		returns connection Object
		"""
		client = paramiko.SSHClient()
		client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
		if ssh_password:
			client.connect(hostname=ssh_machine, username=ssh_username, password=ssh_password, look_for_keys=False, allow_agent=False, timeout=10)
		else:
			client.connect(hostname=ssh_machine, username=ssh_username, allow_agent=True, timeout=10)
		return client

	def run_command(self, ssh_username, ssh_password, ssh_machine, command="ls", jobid="None"):
		"""Executes a command over a established SSH connectio.
		:param ssh_machine: IP of the machine to which SSH connection to be established.
		:param ssh_username: User Name of the machine to which SSH connection to be established..
		:param ssh_password: Password of the machine to which SSH connection to be established..
		returns status of the command executed and Output of the command.
		"""
		conn = self.get_ssh_connection(ssh_machine=ssh_machine, ssh_username=ssh_username, ssh_password=ssh_password)

		stdin, stdout, stderr = conn.exec_command(command=command)

		stdoutput = [line for line in stdout]
		stderroutput = [line for line in stderr]

        # Check exit code.
		if not stdout.channel.recv_exit_status():
			conn.close()
			if not stdoutput:
				stdoutput = True
			return True, stdoutput
		else:
			conn.close()
			return False, stderroutput

	def run_sudo_command(self, ssh_username, ssh_password, ssh_machine, command="ls", jobid="None"):
		"""Executes a command over a established SSH connectio.
		:param ssh_machine: IP of the machine to which SSH connection to be established.
		:param ssh_username: User Name of the machine to which SSH connection to be established..
		:param ssh_password: Password of the machine to which SSH connection to be established..
		returns status of the command executed and Output of the command.
		"""
		conn = self.get_ssh_connection(ssh_machine=ssh_machine, ssh_username=ssh_username, ssh_password=ssh_password)
		command = "sudo -S -p '' %s" % command

		stdin, stdout, stderr = conn.exec_command(command=command)
		if ssh_password:
			stdin.write(ssh_password + "\n")
			stdin.flush()

		stdoutput = [line for line in stdout]
		stderroutput = [line for line in stderr]

        # Check exit code.
		if not stdout.channel.recv_exit_status():
			conn.close()
			if not stdoutput:
				stdoutput = True
			return True, stdoutput
		else:
			conn.close()
			return False, stderroutput
