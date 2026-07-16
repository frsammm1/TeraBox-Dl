import asyncio
from curl_cffi.requests import AsyncSession

async def main():
    async with AsyncSession() as s:
        response = await s.get("https://httpbin.org/bytes/1024", stream=True)
        async for chunk in response.aiter_content():
            print(len(chunk))

asyncio.run(main())
