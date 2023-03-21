import asyncio
import websockets
import json
import logging
from typing import Dict


class DeribitWS:
    def __init__(
        self,
        client_id: str,
        client_secret: str
            ) -> None:
        # Async Event Loop
        self.loop = asyncio.get_event_loop()

        # Instance Variables
        self.ws_connection_url: str = 'wss://test.deribit.com/ws/api/v2'
        self.client_id: str = client_id
        self.client_secret: str = client_secret
        self.websocket_client: websockets.WebSocketClientProtocol = None

    async def ws_auth(self) -> None:
        """
        Requests DBT's `public/auth` to
        authenticate the WebSocket Connection.
        """
        msg: Dict = {
            "jsonrpc": "2.0",
            "id": 9929,
            "method": "public/auth",
            "params": {
                "grant_type": "client_credentials",
                "client_id": self.client_id,
                "client_secret": self.client_secret
            }
        }

        await self.websocket_client.send(
            json.dumps(
                msg
            )
        )

    async def ws_operation(
        self,
        operation: str,
        ws_channel: str
    ):
        async with websockets.connect(
            self.ws_connection_url,
            ping_interval=None,
            compression=None,
            close_timeout=60
        ) as self.websocket_client:
            # Authenticate WebSocket Connection
            await self.ws_auth()

            """
            Requests `public/subscribe` or `public/unsubscribe`
            to DBT's API for the specific WebSocket Channel.
            """
            msg: Dict = {
                "jsonrpc": "2.0",
                "method": f"public/{operation}",
                "id": 42,
                "params": {
                    "channels": [ws_channel]
                }
            }

            while self.websocket_client.open:
                response = await self.websocket_client.recv()
                await self.websocket_client.send(json.dumps(msg))
                response = await self.websocket_client.recv()
                response = await self.websocket_client.recv()
                return json.loads(response)


if __name__ == "__main__":
    # Logging
    logging.basicConfig(
        level='INFO',
        format='%(asctime)s | %(levelname)s | %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
        )

    # DBT LIVE WebSocket Connection URL
    # ws_connection_url: str = 'wss://www.deribit.com/ws/api/v2'
    # DBT TEST WebSocket Connection URL

    # DBT Client ID
    client_id: str = '2F63iPp_'
    # DBT Client Secret
    client_secret: str = 'ElDeEBZ7MtIM3AdMdBITUjfiQcDFKzfMl_VRXp9BbYs'

    DeribitWS(
        client_id=client_id,
        client_secret=client_secret
    )
