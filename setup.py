#!/usr/bin/python3

from setuptools import setup

__author__ = "Md Haris Iqbal"

setup(
	name="do-automate",
	version="0.1.0",
	description="A set of scripts to spin up qemu VMs from linux kernel code",

	author="Md Haris Iqbal",
	author_email="haris.phnx@gmail.com",

	maintainer="Md Haris Iqbal",
	maintainer_email="haris.phnx@gmail.com",

	license="GNU",
	url="https://github.com/ionos-enterprise/testVM",

	packages=['do_automate'],

	install_requires=["paramiko"],

	classifiers = ['Development Status :: 4 - Beta',
		'Environment :: Console',
		'Intended Audience :: Developers',
		'Natural Language :: English',
		'Operating System :: POSIX :: Linux',
		'Programming Language :: Python :: 3',
		'Topic :: Utilities',
	],

	python_requires='>=3',

	entry_points={
		'console_scripts': [
		'do_qemu=do_automate.main:main',
		'do_automate_setup=do_automate.do_setup:setup',
		]
	},
)
