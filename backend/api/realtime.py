from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer


def broadcast_workspace_event(workspace_id: int, payload: dict) -> None:
    channel_layer = get_channel_layer()
    if channel_layer is None:
        return

    async_to_sync(channel_layer.group_send)(
        f"workspace_{workspace_id}",
        {
            "type": "workspace_event",
            "payload": payload,
        },
    )
