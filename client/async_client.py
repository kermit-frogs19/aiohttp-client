import aiohttp
import asyncio
import aiolimiter
import json
from contextlib import nullcontext

from .async_client_response import AsyncClientResponse


class AsyncClient:
    def __init__(
            self,
            base_url: str,
            rate_limit: int = None,
            headers: dict = None,
            timeout: float = 10,
            max_retries: int = 3,
            retry_timeout: float = 10,
            allow_timeout_error_retry: bool = True,
            allow_status_error_retry: bool = False,
            allow_http_error_retry: bool = False,
            allow_json_decode_error_retry: bool = False,
            allow_too_many_reqs_retry: bool = False
    ):
        self.base_url = base_url
        self.headers = headers
        self.rate_limit = rate_limit
        self.max_retries = max_retries
        self.allow_too_many_reqs_retry = allow_too_many_reqs_retry
        self.retry_timeout = retry_timeout

        self.use_request_limit: bool = self.rate_limit is not None
        self.timeout = aiohttp.ClientTimeout(total=timeout)
        self.config: dict = {"timeout": self.timeout, "headers": self.headers}
        self.session = aiohttp.ClientSession(**self.config)
        self.limiter = aiolimiter.AsyncLimiter(self.rate_limit, 1) if self.use_request_limit else None

        self.retryable_errors = list(filter(None, [
            json.JSONDecodeError if allow_json_decode_error_retry else None,
            aiohttp.ContentTypeError if allow_json_decode_error_retry else None,
            asyncio.TimeoutError if allow_timeout_error_retry else None,
            aiohttp.ConnectionTimeoutError if allow_timeout_error_retry else None,
            aiohttp.ClientResponseError if allow_status_error_retry else None,
            aiohttp.ClientError if allow_http_error_retry else None

        ]))

    @property
    def is_running(self) -> bool:
        """
        Returns boolean value of whether the session is still running or not.

        :return: (bool)
        """
        return not self.session.closed

    async def __aenter__(self):
        """Ensures the session is created when entering the context."""

        self.session = aiohttp.ClientSession(**self.config)
        return self  # Allows `async with BaseClient(...) as client:`

    async def __aexit__(self, exc_type, exc_value, traceback):
        """Closes the session when the application exits."""

        if self.session and not self.session.closed:
            await self.stop()

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

    async def _retry(
            self,
            e: BaseException,
            retry_count: int,
            method: str,
            kwargs: dict
    ) -> str | None:
        """
        Checks exception type, async-sleeps for set retry timeout if exception type is set retryable. If max retries
        value if exceeded - returns fail message, else - returns None, signalizing that retry is possible.

        :param e: (BaseException) Exception instance of the BaseException child class
        :param retry_count: (int) Amount of already completed retries
        :param method: (str) Either GET/POST/PUT/PATCH/DELETE
        :param kwargs: (dict) Keyword arguments for the requests
        :return:
        """

        error_name = e.__class__.__name__
        main_message = f"{error_name} {str(e)} in {method}. kwargs: {kwargs}"

        if not isinstance(e, tuple(self.retryable_errors)):
            return f"Non-retryable error: {main_message}"
        elif retry_count == self.max_retries:
            return f"Failed after retrying {retry_count}/{self.max_retries} times. {main_message}"
        elif retry_count < self.max_retries:
            await asyncio.sleep(self.retry_timeout if self.retry_timeout is not None else 2 ** retry_count)
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
        :param kwargs: (dict) Keyword arguments for the requests
        :return: (AsyncClientResponse)
        """

        if not self.is_running:
            await self.start()

        url = url if url.startswith(self.base_url) else f"{self.base_url}{url}"
        use_request_limit = self.use_request_limit if use_request_limit is None else use_request_limit

        for retry_count in range(self.max_retries):
            try:
                async with (self.limiter if use_request_limit else nullcontext()):
                    async with self.session.request(method, url, **kwargs) as response:
                        response.raise_for_status()

                        data = await response.json()
                        text = await response.text()
                        return AsyncClientResponse(code=response.status, text=text, data=data, reason=response.reason)

            except aiohttp.ClientResponseError as e:
                if e.status == 429 and self.allow_too_many_reqs_retry:
                    if fail_message := await self._retry(e, retry_count, method, kwargs):
                        return AsyncClientResponse(code=e.status, _is_error=True, text=f"{fail_message}. text: {e.message}", reason="Too Many Requests")
                else:
                    if fail_message := await self._retry(e, retry_count, method, kwargs):
                        return AsyncClientResponse(code=e.status, _is_error=True, text=f"{fail_message}. text: {e.message}")

            except (json.JSONDecodeError, aiohttp.ContentTypeError, asyncio.TimeoutError,
                    aiohttp.ConnectionTimeoutError, aiohttp.ClientError) as e:
                if fail_message := await self._retry(e, retry_count, method, kwargs):
                    return AsyncClientResponse(_is_error=True, text=fail_message)

            except BaseException as e:
                return AsyncClientResponse(_is_error=True, text=f"BaseException in {method} request - {e.__class__.__name__}: {str(e)}. kwargs: {kwargs}")

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
        :param kwargs: (dict) Keyword arguments for the requests
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
        :param kwargs: (dict) Keyword arguments for the requests
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
        :param kwargs: (dict) Keyword arguments for the requests
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
        :param kwargs: (dict) Keyword arguments for the requests
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
        :param kwargs: (dict) Keyword arguments for the requests
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

        :param url: (str) URL to make HTTP request to
        :param use_request_limit: (bool) Indicate whether the request limiting per time second should be applied
               for the request
        :param kwargs: (dict) Keyword arguments for the requests
        :return: (AsyncClientResponse)
        """

        return await self._request(
            method=method,
            url=url,
            use_request_limit=use_request_limit,
            **kwargs
        )







