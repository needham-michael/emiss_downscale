from setuptools import find_packages, setup

setup(
    name='downscaler',
    version='0.0.1',
    url='https://github.com/needham-michael/emiss_downscale',
    author='Michael Needham',
    author_email='needham.michael@epa.gov',
    description='Methods to downscale photochemical model emissions from coarse to fine grids',
    packages=find_packages(), 
)