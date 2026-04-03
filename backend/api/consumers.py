from channels.generic.websocket import AsyncJsonWebsocketConsumer
from django.contrib.auth.models import AnonymousUser
from asgiref.sync import sync_to_async

from .models import WorkspaceMember


class WorkspaceJobsConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        user = self.scope.get("user")
        if not user or isinstance(user, AnonymousUser) or not user.is_authenticated:
            await self.close(code=4401)
            return

        workspace_id = self.scope["url_route"]["kwargs"].get("workspace_id")
        try:
            self.workspace_id = int(workspace_id)
        except (TypeError, ValueError):
            await self.close(code=4400)
            return

        has_membership = await sync_to_async(
            WorkspaceMember.objects.filter(
                user_id=user.id,
                workspace_id=self.workspace_id,
            ).exists
        )()
        if not has_membership:
            await self.close(code=4403)
            return

        self.group_name = f"workspace_{self.workspace_id}"
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()
        await self.send_json(
            {
                "event_type": "connection.ready",
                "workspace_id": self.workspace_id,
            }
        )

    async def disconnect(self, close_code):
        group_name = getattr(self, "group_name", None)
        if group_name:
            await self.channel_layer.group_discard(group_name, self.channel_name)

    async def workspace_event(self, event):
        payload = event.get("payload", {})
        await self.send_json(payload)
