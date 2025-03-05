import asyncio


# Example usage
class PlaceholderClient(AsyncClient):
    def __init__(self):
        super().__init__(base_url="https://jsonplaceholder.typicode.com")

    async def get_todos(self):
        response = await self.get("/todos")
        print(response)
        if response.is_error:
            print("unsuccessful request :(")
            return None
        return response.data


async def func():
    placeholder = PlaceholderClient()
    result = await placeholder.get_todos()
    print(result)
    await placeholder.stop()

# Press the green button in the gutter to run the script.
if __name__ == '__main__':
    asyncio.run(func())