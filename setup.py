#!/usr/bin/env python
# -*- coding: utf-8 -*-

from setuptools import setup

with open('README.rst') as readme_file:
    readme = readme_file.read()

with open('HISTORY.rst') as history_file:
    history = history_file.read()

requirements = [
    'pyyaml'
]

test_requirements = [
    # TODO: put package test requirements here
]

setup(
    name='kankube',
    version='0.3.1',
    description="Basic kubectl wrapper",
    long_description=readme + '\n\n' + history,
    author="Kando Limited",
    author_email='admin@kando.io',
    url='https://github.com/kandoio/kankube',
    py_modules=['kankube'],
    entry_points={
        'console_scripts': [
            'kankube = kankube:main'
        ]
    },
    install_requires=requirements,
    license="BSD license",
    zip_safe=False,
    keywords='kankube',
    classifiers=[
        'Development Status :: 2 - Pre-Alpha',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: BSD License',
        'Natural Language :: English',
        "Programming Language :: Python :: 2",
        'Programming Language :: Python :: 2.6',
        'Programming Language :: Python :: 2.7',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.3',
        'Programming Language :: Python :: 3.4',
        'Programming Language :: Python :: 3.5',
    ],
    test_suite='tests',
    tests_require=test_requirements
)
