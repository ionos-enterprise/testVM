do_automate scripts
===================

Usage
=====
python3 do_qemu.py <path_to_config_file>


This collection of scripts performs 2 steps
===========================================
Step 1
------
Following are the actions performed in step 1 \
a) Clone the git repo provided (liux kernel) \
b) "make bzImage" for the cloned kernel \
c) Copy the bzImage to our data folder to be used later

Step 2
------
a) Spin up number of VMs using the qcow image and the bzImage kernel (from step 1). Number of VMs taken from the config file. \
b) Configure softROCE on those VMs, and create a softROCE rdma port on the eth interface. \
c) Return the IPs of the VMs, on which the rdma is configured. \

These IPs can now be used as RDMA ports


Config
======

Script config
-------------
The script reads the configuration from the YAML config file given as a command line argument.
Description of the parameters below,
1. Git repository with the kernel including IBNBD patches
2. The path to the qcow image of the VM
3. block device name of the VM on which the os is installed (sda1)
4. host bridge name for networking
5. VM root username and password
6. Number of VMs to be launched and configured in step 2
7. Number of cpu and RAM for VMs in step 2
A sample config file is present in the main folder, named "config-sample.yml".

Kernel config
-------------
A default ".config" file is present with the name "default_kernel_config_file". \
This has the needed modules enabled. \
The make in step 1 uses this config file. \

Prechecks before running the script
===================================
* Always keep a backup of the qcow image

Host
----
package requirements \
	qemu libncurses-dev flex bison openssl libssl-dev dkms libelf-dev libudev-dev libpci-dev libiberty-dev autoconf

qcow VM
-------
package requirements \
	openssh-server \
start sshd server \
bridged networking working - Check this by launching a qemu VM and making sure connectivity is there between the host and the VM. qemu command sample is present at the bottom of this text

Remember
========
* Create a new "config.yml" and use that as a config file. Do not use the file "config-sample.yml". It is just a sample, and is tracked by git.
* Do not forget to shutdown the VMs created in step 1, after using them.
* If step 1 is to be skipped, replace the git_repo in the config file with an empty string. Do keep a valid bzImage in the "data" folder in such case.
* In case of failure and exit of the script, there is a slight chance that there might be a qemu VM running at the background. Use "ps -aux | grep qemu" to identify and kill those orphan VMs.

qemu command sample
===================
"sudo qemu-system-x86_64 -enable-kvm -smp 4 -m 8192M -nographic -snapshot -drive id=d0,file=ubuntu.qcow2,if=none,format=qcow2 -device virtio-blk-pci,drive=d0,scsi=off -kernel bzImage -append "root=/dev/sda1 console=ttyS0" -net nic,macaddr=52:54:00:12:43:12 -net bridge,br=br0"
