#!/usr/bin/env python
# -*- coding: utf-8 -*-

from setuptools import setup

setup(name='herald',
      version='0.1.0',
      description='Haproxy load feedback and check agent',
      url='https://github.com/helpshift/herald',
      download_url='https://github.com/helpshift/herald/tarball/0.1.0',
      author='Raghu Udiyar',
      author_email='raghusiddarth@gmail.com',
      license='MIT',
      packages=['herald', 'herald.plugins'],
      install_requires=['gevent==1.0.2',
                        'pyyaml==3.11'],
      package_data={'herald.plugins': ['*.py']},
      entry_points={
          'console_scripts': [
              'herald = herald.herald:main'
          ]
      },
      keywords=['Haproxy']
      )
