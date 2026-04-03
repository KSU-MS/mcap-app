from django.urls import re_path

from .consumers import WorkspaceJobsConsumer


websocket_urlpatterns = [
    re_path(
        r"^ws/workspaces/(?P<workspace_id>\d+)/jobs/$",
        WorkspaceJobsConsumer.as_asgi(),
    ),
]
