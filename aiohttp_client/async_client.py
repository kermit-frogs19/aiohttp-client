import aiohttp
import asyncio
import aiolimiter
import json
from contextlib import nullcontext
import atexit

from aiohttp_client.async_client_response import AsyncClientResponse


class AsyncClient:
    def __init__(
            self,
            base_url: str = "",
            rate_limit: int = None,
            headers: dict = None,
            timeout: float = 10.0,
            max_attempts: int = 3,
            retry_timeout: float = 10.0,
            allow_timeout_error_retry: bool = True,
            allow_status_error_retry: bool = False,
            allow_http_error_retry: bool = False,
            allow_json_decode_error_retry: bool = False,
            allow_too_many_reqs_retry: bool = False
    ) -> None:
        """
        HTTP client, makes requests, returns responses. Includes functionalities of request rate limiting and
        request retrying, when an error (which is set as retryable) occurs. Request methods return an instance of
        AsyncClientResponse class.

        :param base_url: (str) Base part of URL to make requests to. If methods get full URL, base part of which is
               already set in this variable, then the base URL set here is ignored.
        :param rate_limit: (int) Request rate limiting. Amount of HTTP requests per second the client will do. If set to
               None, then rate limiting is not applied, thus rate limiting is not applied by default.
        :param headers: (dict, Optional) Headers that will be used when making request. If not provided, then
               headers must be passed to methods when making requests.
        :param timeout: (float, int) Request timeout, how long do the client waits for connection to be established with
               the server/get a response from server.
        :param max_attempts: (int) Maximum amount of attempts the client will take to get a successful response from a
               server, if the initial request was unsuccessful and the request error is set as retryable.
        :param retry_timeout: (float, int) Amount of time, in seconds, the client will wait before retrying request. If
               set to None, then client uses exponentially increasing delays between retries. If set to 0, then retry
               timeout is not applied.
        :param allow_timeout_error_retry: (bool) Indicates whether the timeout errors should be retried or not.
        :param allow_status_error_retry: (bool) Indicates whether the status errors (returned by the server) should
               be retried or not.
        :param allow_http_error_retry: (bool) Indicates whether the general HTTP errors should be retried or not.
        :param allow_json_decode_error_retry: (bool) Indicates whether the requests that didn't get a valid JSON data
               in response should be retried or not.
        :param allow_too_many_reqs_retry: (bool) Indicates whether the requests that got '429 - Too Many Requests'
               error should be retried.
        """

        self.base_url = base_url
        self.headers = headers
        self.rate_limit = rate_limit
        self.max_attempts = max_attempts
        self.allow_too_many_reqs_retry = allow_too_many_reqs_retry
        self.retry_timeout = retry_timeout

        self.use_request_limit: bool = self.rate_limit is not None
        self.timeout = aiohttp.ClientTimeout(total=timeout)
        self.config = {"timeout": self.timeout, "headers": self.headers}
        self.session = None
        self.limiter = aiolimiter.AsyncLimiter(self.rate_limit, 1) if self.use_request_limit else None

        self.retryable_errors = list(filter(None, [
            json.JSONDecodeError if allow_json_decode_error_retry else None,
            aiohttp.ContentTypeError if allow_json_decode_error_retry else None,
            asyncio.TimeoutError if allow_timeout_error_retry else None,
            aiohttp.ConnectionTimeoutError if allow_timeout_error_retry else None,
            aiohttp.ClientResponseError if allow_status_error_retry else None,
            aiohttp.ClientError if allow_http_error_retry else None,
            aiohttp.ClientConnectionError if allow_timeout_error_retry else None
        ]))

        atexit.register(self._force_stop)  # Ensure cleanup on exit

    async def __aenter__(self):
        """
        Ensures the session is created when entering the context. For use with async context manager, i.e.

        `async with AsyncClient() as client`
        """

        self.session = aiohttp.ClientSession(**self.config)
        return self  # Allows `async with AsyncClient(...) as client:`

    async def __aexit__(self, exc_type, exc_value, traceback):
        """
        Closes the session when the application exits the context.For use with async context manager, i.e.

        `async with AsyncClient() as client`
        """

        if self.session and not self.session.closed:
            await self.stop()

    def _force_stop(self):
        """ Sync close for atexit handling """
        if self.is_running:
            loop = asyncio.get_event_loop()
            loop.run_until_complete(self.stop())

    async def _retry(
            self,
            e: BaseException,
            attempt_count: int,
            method: str,
            kwargs: dict
    ) -> str | None:
        """
        Checks exception type, async-sleeps for set retry timeout if exception type is set as retryable. If max retries
        value if exceeded - returns fail message, else - returns None, signalizing that retry is possible.

        :param e: (BaseException) Exception instance of the BaseException child class
        :param attempt_count: (int) Amount of already completed retries
        :param method: (str) Either GET/POST/PUT/PATCH/DELETE
        :param kwargs: (dict) Keyword arguments for the requests
        :return: None
        """

        error_name = e.__class__.__name__
        main_message = f"{error_name} {str(e)} in {method} method. kwargs: {kwargs}"

        if not isinstance(e, tuple(self.retryable_errors)):
            return f"Non-retryable error: {main_message}"
        elif attempt_count == self.max_attempts:
            return f"Failed after attempting {attempt_count}/{self.max_attempts} times. {main_message}"
        elif attempt_count < self.max_attempts:
            await asyncio.sleep(self.retry_timeout if self.retry_timeout is not None else 2 ** attempt_count)
            return None
        return main_message

    async def _request(
            self,
            method: str,
            url: str,
            use_request_limit: bool = None,
            **kwargs
    ) -> AsyncClientResponse:
        """
        Main method for making HTTP requests

        :param method: (str) Either GET/POST/PUT/PATCH/DELETE
        :param url: (str) URL to make HTTP request to
        :param use_request_limit: (bool) Indicate whether the request limiting per time second should be applied
               for the request
        :param kwargs: (dict) Additional keyword arguments for the requests. Use standard aiohttp parameters.
        :return: (AsyncClientResponse)
        """

        if not self.is_running:
            await self.start()

        url = url if url.startswith(self.base_url) else f"{self.base_url}{url}"
        use_request_limit = self.use_request_limit if use_request_limit is None else use_request_limit

        for attempt in range(1, self.max_attempts + 1):
            try:
                async with (self.limiter if use_request_limit else nullcontext()):
                    async with self.session.request(method, url, **kwargs) as response:
                        text = await response.text()
                        response.raise_for_status()

                        data = await response.json()
                        return AsyncClientResponse(code=response.status, text=text, data=data, reason=response.reason)

            except aiohttp.ClientResponseError as e:
                if e.status == 429 and self.allow_too_many_reqs_retry:
                    if fail_message := await self._retry(e, attempt, method, kwargs):
                        return AsyncClientResponse(code=e.status, _is_error=True, text=f"{fail_message}. text: {text}", reason="Too Many Requests")
                else:
                    if fail_message := await self._retry(e, attempt, method, kwargs):
                        return AsyncClientResponse(code=e.status, _is_error=True, text=f"{fail_message}. text: {text}")

            except (json.JSONDecodeError, aiohttp.ContentTypeError, asyncio.TimeoutError,
                    aiohttp.ConnectionTimeoutError, aiohttp.ClientError, aiohttp.ClientConnectionError) as e:
                if fail_message := await self._retry(e, attempt, method, kwargs):
                    return AsyncClientResponse(_is_error=True, text=fail_message)

            except BaseException as e:
                return AsyncClientResponse(_is_error=True, text=f"BaseException in {method} request - {e.__class__.__name__}: {str(e)}. kwargs: {kwargs}")

    @property
    def is_running(self) -> bool:
        """
        Returns boolean value of whether the session is still running or not.

        :return: (bool)
        """
        if self.session is None:
            return False
        return not self.session.closed

    async def start(self) -> None:
        """Starts the client, if closed"""

        if self.is_running:
            return

        self.session = None
        self.session = aiohttp.ClientSession(**self.config)

    async def stop(self) -> None:
        """Stops the client, if running"""

        if not self.is_running:
            return

        await self.session.close()
        self.session = None

    async def get(
            self,
            url: str = "",
            use_request_limit: bool = None,
            **kwargs
    ) -> AsyncClientResponse:
        """
        HTTP Request of the GET method. Makes an async request and returns request response.

        :param url: (str) URL to make HTTP request to
        :param use_request_limit: (bool) Indicate whether the request limiting per time second should be applied
               for the request
        :param kwargs: (dict) Additional keyword arguments for the requests. Use standard aiohttp parameters.
        :return: (AsyncClientResponse)
        """

        return await self._request(
            method="GET",
            url=url,
            use_request_limit=use_request_limit,
            **kwargs
        )

    async def post(
            self,
            url: str = "",
            use_request_limit: bool = None,
            **kwargs
    ) -> AsyncClientResponse:
        """
        HTTP Request of the POST method. Makes an async request and returns request response.

        :param url: (str) URL to make HTTP request to
        :param use_request_limit: (bool) Indicate whether the request limiting per time second should be applied
               for the request
        :param kwargs: (dict) Additional keyword arguments for the requests. Use standard aiohttp parameters.
        :return: (AsyncClientResponse)
        """

        return await self._request(
            method="POST",
            url=url,
            use_request_limit=use_request_limit,
            **kwargs
        )

    async def put(
            self,
            url: str = "",
            use_request_limit: bool = None,
            **kwargs
    ) -> AsyncClientResponse:
        """
        HTTP Request of the PUT method. Makes an async request and returns request response.

        :param url: (str) URL to make HTTP request to
        :param use_request_limit: (bool) Indicate whether the request limiting per time second should be applied
               for the request
        :param kwargs: (dict) Additional keyword arguments for the requests. Use standard aiohttp parameters.
        :return: (AsyncClientResponse)
        """

        return await self._request(
            method="PUT",
            url=url,
            use_request_limit=use_request_limit,
            **kwargs
        )

    async def patch(
            self,
            url: str = "",
            use_request_limit: bool = None,
            **kwargs
    ) -> AsyncClientResponse:
        """
        HTTP Request of the PATCH method. Makes an async request and returns request response.

        :param url: (str) URL to make HTTP request to
        :param use_request_limit: (bool) Indicate whether the request limiting per time second should be applied
               for the request
        :param kwargs: (dict) Additional keyword arguments for the requests. Use standard aiohttp parameters.
        :return: (AsyncClientResponse)
        """

        return await self._request(
            method="PATCH",
            url=url,
            use_request_limit=use_request_limit,
            **kwargs
        )

    async def delete(
            self,
            url: str = "",
            use_request_limit: bool = None,
            **kwargs
    ) -> AsyncClientResponse:
        """
        HTTP Request of the DELETE method. Makes an async request and returns request response.

        :param url: (str) URL to make HTTP request to
        :param use_request_limit: (bool) Indicate whether the request limiting per time second should be applied
               for the request
        :param kwargs: (dict) Additional keyword arguments for the requests. Use standard aiohttp parameters.
        :return: (AsyncClientResponse)
        """

        return await self._request(
            method="DELETE",
            url=url,
            use_request_limit=use_request_limit,
            **kwargs
        )

    async def request(
            self,
            method: str,
            url: str = "",
            use_request_limit: bool = None,
            **kwargs
    ) -> AsyncClientResponse:
        """
        Makes an async request and returns request response.

        :param method: (str) HTTP Method that should be to make request, either GET/POST/PUT/PATCH/DELETE
        :param url: (str) URL to make HTTP request to
        :param use_request_limit: (bool) Indicate whether the request limiting per time second should be applied
               for the request
        :param kwargs: (dict) Additional keyword arguments for the requests. Use standard aiohttp parameters.
        :return: (AsyncClientResponse)
        """

        return await self._request(
            method=method,
            url=url,
            use_request_limit=use_request_limit,
            **kwargs
        )







