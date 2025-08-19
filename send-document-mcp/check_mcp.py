#!/usr/bin/env python3
import asyncio
from mcp.client.streamable_http import streamablehttp_client
from mcp.client.session import ClientSession

SERVER_URL = "http://localhost:8000"


async def main():
    async with streamablehttp_client(SERVER_URL) as (read_stream, write_stream, _):
        async with ClientSession(read_stream, write_stream) as session:
            init_resp = await session.initialize()
            print("Session initialized:", init_resp)

            tools = await session.list_tools()
            print("\nAvailable Tools:")
            for t in tools:
                if hasattr(t, 'name'):
                    print(f"  • {t.name}: {getattr(t, 'description', 'No description')}")
                else:
                    print(f"  • {t}")


if __name__ == "__main__":
    asyncio.run(main())


