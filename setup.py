from setuptools import setup
from __init__ import __version__, __name__

setup(
    name=__name__,
    version=__version__,
    py_modules=["async_client", "async_client_response", "example"],
    install_requires=["aiohttp", "aiolimiter"],
)