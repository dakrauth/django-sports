#!/usr/bin/env python
import os
import sys
from setuptools import find_packages, setup

if sys.argv[-1] == 'publish':
    if os.system('python setup.py sdist bdist_wheel'):
        raise RuntimeError('Unable to build distribution')

    if os.system('python -m twine upload dist/*'):
        raise RuntimeError('Unable to upload distribution')

    sys.exit(0)


with open('README.rst', 'r') as f:
    long_description = f.read()

# Dynamically calculate the version based on sports.VERSION.
version = __import__('sports').get_version()

setup(
    name='django-sports',
    url='https://github.com/dakrauth/django-sports',
    author='David A Krauth',
    author_email='dakrauth@gmail.com',
    description='A Django sports team and league modeling app',
    version=version,
    long_description=long_description,
    platforms=['any'],
    license='MIT License',
    classifiers=(
        'License :: OSI Approved :: MIT License',
        'Environment :: Web Environment',
        'Framework :: Django',
        'Framework :: Django :: 2.2',
        'Programming Language :: Python',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.5',
        'Programming Language :: Python :: 3.6',
        'Programming Language :: Python :: 3.7',
    ),
    packages=find_packages(),
    include_package_data=True,
    zip_safe=False,
    install_requires=[
        'Django>=2.2',
        'choice-enum==1.0.0',
        'Pillow>=6.1.0',
        'python-dateutil>=2.8.0'
    ],
)
