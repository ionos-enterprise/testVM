do_automate
===========
do_automate is a set of scripts which takes path/url to Linux kernel code, builds it and spins up VMs with that code.
It also has an option to include out-of-tree modules while spinning up VMs, which can be then inserted and used inside the VM.

Explore the code
================
The code for do_automate is at the following git repo. Feel free to explore.
https://github.com/ionos-enterprise/testVM

Installation
=========
To install do_automate, clone the code, navigate to the location and run the following command.

    $ sudo pip install .

Setup
=====
After installing the do_automate package, it is recommended to run the setup script. This will perform a number of crucial steps to make sure things work properly. Before execution of every step, the setup script outputs the action/command that would be executed and asks for a response (skip, continue, exit). This is to make sure that the setup script does not mess up anything in current configuration.

    $ do_automate_setup

It is safe to stop the execution of the setup script when it asks for a response and run it again; in cases one wants to check out stuff manually.

Steps performed by the setup script
------------------------------------
1) Install packages needed for kernel make, qemu and libvirt.

2) Check and configure network bridges to be used by qemu for VM networking.
When libvirt stuff is installed, it creates one network bridge by default; named "default" (interface name "virbr0"). Since some of our tests require test machines to have 2 network interfaces, another network bridge has to be added, with a different subnet.
The setup script uses settings from "default" bridge, changes stuff like uuid, IP, subnet, and adds another bridge named "bridge_2" (interface name "virbr1").

3) Insert kvm related modules.

Requirements
============
To spin up VMs through do_automate, one basically need 2 things. A qcow image with the base filesystem installed, and kernel code to make and use the bzImage from.

Qcow Image
----------
One can create a debian image to be used by do-automate using the below command (Requires debootstrap package).

	$ do_automate_setup -i

The above qcow is created with the root filesystem on block device vda1, and with username/password set to root/root.

Kernel code
-----------
For the kernel code. One can provide the local absolute path to a directory containing the checked out kernel code, or a git URL of the kernel code.

Checklist
=========
1) Check bridges and their network interfaces. They should look something like this,

        $ sudo virsh net-info default
        Name: default
        UUID: 60dda92f-1cc7-4503-991a-xxxxxxxxxxx
        Active: yes
        Persistent: yes
        Autostart: yes
        Bridge: virbr0

        $ sudo virsh net-info bridge_2
        Name: bridge_2
        UUID: 60dda92f-1cc7-4503-991a-xxxxxxxxxxx
        Active: yes
        Persistent: yes
        Autostart: yes
        Bridge: virbr1

        $ ip a
        .
        .
        4: virbr0: <NO-CARRIER,BROADCAST,MULTICAST,UP> mtu 1500 qdisc noqueue state DOWN group default qlen 1000
        link/ether 52:54:00:db:f5:ae brd ff:ff:ff:ff:ff:ff
        inet 192.168.122.1/24 brd 192.168.122.255 scope global virbr0
        valid_lft forever preferred_lft forever
        .
        .
        6: virbr1: <NO-CARRIER,BROADCAST,MULTICAST,UP> mtu 1500 qdisc noqueue state DOWN group default qlen 1000
        link/ether 52:54:00:db:f5:ad brd ff:ff:ff:ff:ff:ff
        inet 192.168.123.1/24 brd 192.168.123.255 scope global virbr1
        valid_lft forever preferred_lft forever
        .
        .

"state DOWN" for the network interfaces is fine, since they will be used only as bridges.

First run
=========
Assuming one has fulfilled and read the above points, its time to test run the script.
The do_qemu is used to build kernel and spin up VMs. It takes a json config file with the required structure and values filled in. The json config file has the below structure,

    {
        "server-class-1": {
            "mode":         "snapshot",

            "num_of_cpu": 4,
            "ram_size": 8192,

            "qcow":         "/home/test/debian_new.qcow2",
            "block_dev":    "vda1",
            "username":     "root",
            "password":     "root",

            "bridges":      ["virbr0","virbr1"],

            "kernel_code":  "/home/test/linux/",
            "modules":      ["/home/test/abc/"]
        },
        "storage-class-1": {
            "mode":         "persistent",

            "num_of_cpu": 4,
            "ram_size": 8192,

            "qcow":         "/home/test/debian_new.qcow2",
            "block_dev":    "vda1",
            "username":     "root",
            "password":     "root",

            "bridges":      ["virbr0","virbr1"],

            "kernel_code":  "/home/test/linux/",
            "modules":      ["/home/test/abc/"],
            "scsi_images":  ["/home/test/disk2.qcow2"]
        },
        "server": {
            "vm_class": "server-class-1",
            "num_of_vm": 2
        },
        "storage": {
            "vm_class": "storage-class-1",
            "num_of_vm": 1
        },
        "log_level": "INFO"
    }

To start the script with the above json config file, run,

    $ do_qemu -f config.json

Lets briefly look at the parameters for better understanding.

The **"server"** and **"storage"** sections are the ones which pick up which **"vm_class"** to use to spin up VMs.

Also, **"num_of_vm"** specify the number of VMs to be launched of that class.

The classes of VM is specified separately above, namely **"server-class-1"** and **"storage-class-1"**. One can have a number of such classes defined, and conveniently pick 2 of them as described above.

Inside each VM class, the parameters defined are discussed below.

**"mode"**
This option allows the user to choose how to run the VMs. Accepted values are **"snapshot"** or **"persistent"**.
In snapshot mode, each VM starts with *-snapshot* flag. No changes are saved to the image in this mode.
In persistent mode each VM runs with its own copy of the qcow images, and the changes made to the VM (its qcow) are persisted between runs.

**"num_of_cpu", "ram_size"**
These are related to the VMs being spun up. Number of VMs, CPUs for each VM and RAM for each VM respectively.
These are required parameters.

**"qcow", "block_dev"**
These are related to the qcow image.
"qcow" takes the path to the qcow image. "block_dev" takes the partition name where the root filesystem resides in the qcow image.

**"username", "password"**
Username and password for the VM.
If the username parameter is dropped, then the script uses "root" as default choice.
The password parameter can be dropped if one wishes to use ssh keys for login.

**"bridges"**
The two bridges to be used for the two network interfaces of each VM.

**"kernel_code"**
Absolute path to the local folder containing the Linux code. This folder should contain the kernel config file ".config"
A git URL can also be passed to this. Example,

    "kernel_code": "https://github.com/torvalds/linux.git"
In this case the ".config" file copied from the "/boot/" folder of the host machine.

**"modules"**
Out of tree modules to be included in the VM. Discussed in the next section.

**"log_level"**
This can be used to control the logging to the console. The options are *"ERROR"*, *"INFO"* and *"DEBUG"*. Level *"ERROR"* being the least verbose, and *"DEBUG"* being the most.

Once the script is done, it will output the IPs of the VM. One can use these IPs to login to the VM.

    Server VM IPs: [['192.168.122.210', '192.168.123.127']]
    Storage VM IPs: [['192.168.122.82', '192.168.123.125']]

Using do_automate with out-of-tree kernel module
================================================
Along with spinning up with VMs using kernel code; do_automate can also add out-of-tree kernel modules to the mix, so that they can be inserted and used inside the VM.

To do this, simply fill the **"modules"** param value in the json config file with the absolute path where the out-of-tree kernel module resides. Do make sure that the module builds successfully with the kernel code whose path is kept as the value in the **"kernel_code"** param, else the script will fail.

Example,

    "modules":      ["/home/test/abc/"]

If multiple modules are to be provided, simply add their absolute paths to the module param list. For example,

    "modules":      ["/home/test/abc/", "/home/test/def/"]

**"modules"**
Absolute path to the module abc, which would be installed and available for the VM to modprobe.

SCSI Images
===========
While one can always create loop/ram devices inside the VM, or use nullblk devices; sometimes there is a need to have proper scsi block devices, which would have persistent storage, and can keep the data across reboots and restarts of VMs.
NOTE: To persist changes made to the scsi images, spin up VMs in **"persistent"** mode. In **"snapshot"** mode, the changes made to these scsi images will not be persisted.

do-automate has an option to provide extra qcow images to be used as scsi block devices. The VMs would then come up with these images connected as scsi block devices.
To provide extra qcow images, add the following option in the json configuration file for that particular VM.

    "scsi_images":  ["/home/test/disk1.qcow2"]

For multiple images, add multiple paths to the above list,

    "scsi_images":  ["/home/test/disk1.qcow2","/home/test/disk2.qcow2"]

You can create the qcow image file with the following command,

    # qemu-img create -f qcow2 disk1.qcow2 100M

Build options
=============
The default behaviour of do-automate is to always perform the make and install steps for the kernel and the modules included in the json config. But not every run requires the build and install of kernel and modules. Sometimes there is no change at all in the code and hence no build is required. do-automate provides a way for the user to skip some steps and jump directly to spinning up the VMs and their configuration.

There are 3 main steps that do-automate performs.
1) Building the kernel and performing **"make modules_install && make install"**.
2) Building the out-of-tree modules and performing **"make modules_install"**.
3) Spinning up VMs and configuring them.

The user can choose to skip the first and the second steps and jump directly to the third one. Note that the user must have performed the first and the second steps atleast once; which would create the bzImage and install all the modules in place for the VM to find.
Selecting the build options can be done with the **"-b --build"** command line parameter. Following are the options

- all     -       Build kernel, modules, spin up VMs. This is the default option when nothing is provided
- kernel  -       Build kernel, spin up VMs
- module  -       Build modules, spin up VMs. Should have the necessary stuff (bzImage, kernel modules installed).
- run     -       Spin up VMs (build nothing). Should have the necessary stuff (bzImage, kernel modules installed).

Example,

    $ do_qemu -f sample.json -b <all|kernel|module|run>
NOTE: The user must have performed the first and the second steps atleast once; which would create the bzImage and install all the modules in place for the VM to find.

Optional parameters
===================
Pipes (WIP)
-----------
This feature was added for use cases when the network communication with the VM goes down. In such a case, commands cant be sent to the VM through ssh, and the only was to stop the VM would be the **"kill"** command.
When pipes are enabled, the VM would be created with serial communication opened, which can be used to execute commands and get the output back.
To enable pipes, add the following lines in the json configuration of a VM,

    "optional":     ["pipe"]

NOTE: Configuring pipes takes time; hence when this option is enabled, spinning up and configuration of VM would take more time then usual. This feature is disabled by default.

VM details
==========
One can use the **"-s --show"** command line parameter to get the details of the running VMs.

    $ do_qemu -s
	Log file  /home/test/do_automate_data//logs/log_...
    {'676f39b1-4d1e-435a-a82e-e9439ad56df8': {'base_image': '/home/test/debian_new.qcow2,
                                          'bridges': ['virbr0', 'virbr1'],
                                          'ips': ['192.168.122.76',
                                                  '192.168.123.77'],
                                          'kernel_code': '/home/test/linux/,
                                          'macs': ['52:54:00:12:43:10',
                                                   '52:54:00:12:43:11'],
                                          'mode': 'persistent',
                                          'optional': [],
                                          'pid': 36505,
                                          'scsi_images': ['/home/test/disk2.qcow2'],
                                          'shared_9p_tag': 'storehost',
                                          'state': 'Network Up',
                                          'vm_name': 'storage-class-1',
                                          'vm_num': 0,
                                          'vm_type': 'storage'},
     'a9390684-1452-47b8-a26e-f5dc8bfbad4b': {'base_image': '/home/test/debian_new.qcow2',
                                          'bridges': ['virbr0', 'virbr1'],
                                          'ips': ['192.168.122.74',
                                                  '192.168.123.75'],
                                          'kernel_code': '/home/test/linux/',
                                          'macs': ['52:54:00:12:43:12',
                                                   '52:54:00:12:43:13'],
                                          'mode': 'persistent',
                                          'optional': [],
                                          'pid': 36888,
                                          'shared_9p_tag': 'serverhost',
                                          'state': 'Network Up',
                                          'vm_name': 'server-class-1',
                                          'vm_num': 0,
                                          'vm_type': 'server'}
	}

	$ do_qemu -s ip
    Log file  /root/do_automate_data//logs/...
    storage-class-1	192.168.122.76	192.168.123.77
    server-class-1	192.168.122.74	192.168.123.75

NOTE: If the VMs are shutdown manually, there is a chance that the above command would show VM details which are not up. See "Shutdown and reboot" section below.

Shutdown and reboot
===================
do-qemu command can also be used to shutdown and reboot the VMs.
Of the two, reboot is more important, since there are a number of configurations that do-automate performs on those VMs. In case one manually reboots the VM, those configurations are lost and the VM would not work. So it is essential to perform reboot through do-automate command. One can reboot VMs using the following command,

    $ do_qemu -C reboot <vm1-ip>,vm2-ip>,...

Shutdown is similar to the above command, and simply shutdowns the VM. The advantage of shutting down the VM through the do-qemu command is that do-automate would have a better overview of which VM is still running and which ones have been shutdown.
Note that one can use the "all" option to shutdown/reboot all the running VMs.

    $ do_qemu -C shutdown all
    $ do_qemu -C shutdown a

do_automate data
================
do_automate creates a folder named "do_automate_data". This serves as a place to stores data related to the script. The default location of this folder is "~/", but can be changed by setting the environmental variable DO_AUTOMATE_DATA.

Notably, it contains the following folders and data.

**linux folder**

This folder has 2 variants. One for the server class of VMs, and another for the storage class of VMs. Both are prefixed with their class names accordingly (serv_linux, stor_linux).
This is used to check out the Linux code if one provides a url to -k option. Also the bzImage of the built kernel is copied to this folder.

**vm_share folder**

This folder also has 2 variants like the linux folder (serv_vm_share, stor_vm_share).
This contains the folder lib, containing the kernel modules of the kernel built. This is shared with the VM of the respective class.

**vm_imgs**

This folder stores the debian qcow image when using VMs in persistent mode.
When the VMs are being used in persistent mode, the same qcow image cannot be used for different VMs, since they are opened in read-write mode by qemu. In such a case, do-automate copies the image to this folder (specific storage or server accordingly), and then uses them to spin up the persistent VMs.

**pipes folder**

This folder contains the pipes for running VMs. For each VM there are 2 pipes, in and out. They are named after the uuid of the respective VM.

**vm_details.json**

This file contains the details of the running VM. This is used by do_automate later when a shutdown or a reset of a VM is triggered.

This files contains the IPs, mac addresses and bridges of the VM.

**The logs folder**

This contains the logs of do_automate runs.

Please note
===========
1) The path for the parameters -k and -m should be absolute. Relative path does not work sometimes, and should be avoided for now.

2) After spinning up and using the VMs. Do shut them down.
Sometimes it so happens that the VM gets stuck while shutting down. Or while testing something inside the VM, the networking gets messed up and one can no longer login to issue the shutdown command. In such a case, check the running qemu processed and kill them.

        $ ps -aux | grep qemu
        $ sudo kill -9 <proc-id>

qemu command sample
===================
    $ sudo qemu-system-x86_64 -smp {cpu} -m {ram}M -nographic -snapshot \
                -drive id=d0,file=debian.qcow,if=none,format=qcow2 \
                -device virtio-blk-pci,drive=d0,scsi=off -kernel bzImage \
                -append 'root=/dev/sda1' \
                -netdev bridge,br=virbr0,id=id0 -device virtio-net,netdev=id0,mac=52:54:00:12:43:a2 \
                -netdev bridge,br=virbr1,id=id1 -device virtio-net,netdev=id1,mac=52:54:00:12:43:a3 \
                -virtfs local,path=/tmp/data/,mount_tag=host0,security_model=passthrough,id=d1,readonly
