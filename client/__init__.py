
__version__ = "1.0.0"


try:
    import aiohttp
except ImportError:
    raise ImportError("aiohttp package must be installed to use the aiohttp-client. use 'pip install aiohttp'")

try:
    import aiolimiter
except ImportError:
    raise ImportError("aiolimiter package must be installed to use the aiohttp-client. use 'pip install aiolimiter'")


from .async_client import AsyncClient
from .async_client_response import AsyncClientResponse

