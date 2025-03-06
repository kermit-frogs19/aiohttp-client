from setuptools import setup, find_packages
from .aiohttp_client import __version__, __name__

setup(
    name=__name__,
    version=__version__,
    packages=find_packages(),
    install_requires=["aiohttp", "aiolimiter"],
)