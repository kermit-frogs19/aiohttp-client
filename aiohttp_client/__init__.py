__version__ = "1.0.0"
__name__ = "aiohttp-client"


try:
    import aiohttp
except ImportError:
    raise ImportError("aiohttp package must be installed to use the aiohttp-client. use 'pip install aiohttp'")

try:
    import aiolimiter
except ImportError:
    raise ImportError("aiolimiter package must be installed to use the aiohttp-client. use 'pip install aiolimiter'")

from aiohttp_client.async_client import AsyncClient
from aiohttp_client.async_client_response import AsyncClientResponse


