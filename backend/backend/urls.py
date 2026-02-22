from django.urls import path, include, re_path
from django.conf import settings
from django.conf.urls.static import static
from rest_framework.routers import DefaultRouter
from api.views import (
    McapLogViewSet,
    ParseSummaryView,
)
from drf_yasg.views import get_schema_view
from drf_yasg import openapi

# ===== ROUTER CONFIGURATION =====
# DefaultRouter automatically creates URLs for ViewSet methods:
# - Standard CRUD: list, create, retrieve, update, partial_update, destroy
# - Custom actions: methods decorated with @action
router = DefaultRouter()

# McapLogViewSet endpoints:
# - GET/POST /api/mcap-logs/ (list, create)
# - GET/PUT/PATCH/DELETE /api/mcap-logs/{id}/ (retrieve, update, partial_update, destroy)
# - GET /api/mcap-logs/{id}/geojson/ (custom action)
# - GET /api/mcap-logs/{id}/job-status/ (custom action)
# - POST /api/mcap-logs/download/ (custom action)
# - POST /api/mcap-logs/batch-upload/ (custom action)
# - GET /api/mcap-logs/job-statuses/ (custom action)
router.register(r"mcap-logs", McapLogViewSet)

# ===== API DOCUMENTATION =====
# Swagger/OpenAPI schema view
schema_view = get_schema_view(
    openapi.Info(
        title="MCAP Query Backend API",
        default_version="v1",
        description="API for querying and managing MCAP log files with GPS tracking",
        terms_of_service="https://www.google.com/policies/terms/",
        contact=openapi.Contact(email="contact@example.com"),
        license=openapi.License(name="BSD License"),
    ),
    public=True,
)

# ===== URL PATTERNS =====
urlpatterns = [
    # API documentation endpoints
    re_path(
        r"^swagger(?P<format>\.json|\.yaml)$",
        schema_view.without_ui(cache_timeout=0),
        name="schema-json",
    ),
    re_path(
        r"^swagger/$",
        schema_view.with_ui("swagger", cache_timeout=0),
        name="schema-swagger-ui",
    ),
    re_path(
        r"^redoc/$", schema_view.with_ui("redoc", cache_timeout=0), name="schema-redoc"
    ),
    # API routes with /api/ prefix (recommended)
    path("api/", include(router.urls)),
    path("api/parse/summary/", ParseSummaryView.as_view(), name="parse-summary"),
    # Root-level routes (for backward compatibility)
    path("", include(router.urls)),
    path("parse/summary/", ParseSummaryView.as_view(), name="parse-summary-root"),
]

# Serve media files in development
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
