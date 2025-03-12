import asyncio

# Importing the client from the package
from async_client import AsyncClient


# Example usage
# Creating a child class of AsyncClient
class PlaceholderClient(AsyncClient):
    def __init__(self):
        super().__init__(
            base_url="https://jsonplaceholder.typicode.com",    # Setting base URL
            rate_limit=1,                                       # Limiting to 1 request per second
            allow_status_error_retry=True,                      # allowing request retries in cases of status error
            retry_timeout=0,                                    # Disabling retry timeout
            headers={"Content-type": "application/json"}        # Adding request headers
        )

    # Using the GET method
    async def get_todos(self):
        # Using url endpoint of base URL. Full URL is also acceptable (https://jsonplaceholder.typicode.com/todos).
        response = await self.get("/todos")
        print(response)

        # Checking the response and accessing its fields
        if response.is_error:
            print("unsuccessful request :(")
            return None

        # Returning resulting data
        return response.data

    async def make_a_post(self, data):
        # POST method example usage
        response = await self.post("/posts", json=data)

        # Checking the response and accessing its fields
        if response.is_error:
            print(f"Failed to make a post {data}...")
            return None
        return response.data


# initializing the child class
placeholder = PlaceholderClient()


async def func():
    # using the method
    result = await placeholder.get_todos()
    print(result)

    # Using the method with asyncio gather and testing batch requesting and rate limiting
    future_results = [
        placeholder.get_todos(),
        placeholder.get_todos(),
        placeholder.get_todos(),
        placeholder.get_todos(),
        placeholder.get_todos(),
        placeholder.get_todos()
    ]

    # Getting and awaiting all request results at once
    results = await asyncio.gather(*future_results)
    print(results)

    # Using the POST method to make a post.
    result = await placeholder.make_a_post({"title": 'foo', "body": 'bar', "userId": 1})
    print(result)

    # Stopping the client
    await placeholder.stop()

# Press the green button in the gutter to run the script.
if __name__ == '__main__':

    # Running the script with asyncio
    asyncio.run(func())

