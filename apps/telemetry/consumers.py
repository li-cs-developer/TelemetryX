import json

from channels.generic.websocket import AsyncWebsocketConsumer


class FleetLiveConsumer(AsyncWebsocketConsumer):
    """
    One group per organization. Ingestion publishes updates to the group;
    every connected dashboard for that org receives them instantly.
    """

    async def connect(self):
        user = self.scope.get("user")
        if not user or not user.is_authenticated or not user.organization_id:
            await self.close(code=4401)
            return

        self.group_name = f"org_{user.organization_id}"
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, code):
        if hasattr(self, "group_name"):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def telemetry_update(self, event):
        # Fired by the ingestion view via channel_layer.group_send
        await self.send(text_data=json.dumps(event["payload"]))