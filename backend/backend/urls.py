from django.urls import path, include, re_path
from django.conf import settings
from django.conf.urls.static import static
from rest_framework.routers import DefaultRouter
from api.views import (
    McapLogViewSet, 
    ParseSummaryView,
    CarViewSet,
    DriverViewSet,
    EventTypeViewSet
)
from drf_yasg.views import get_schema_view
from drf_yasg import openapi

router = DefaultRouter()
router.register(r'mcap-logs', McapLogViewSet)
router.register(r'cars', CarViewSet, basename='car')
router.register(r'drivers', DriverViewSet, basename='driver')
router.register(r'event-types', EventTypeViewSet, basename='event-type')

# Swagger/OpenAPI schema view
schema_view = get_schema_view(
    openapi.Info(
        title="MCAP Query Backend API",
        default_version='v1',
        description="API for querying and managing MCAP log files with GPS tracking",
        terms_of_service="https://www.google.com/policies/terms/",
        contact=openapi.Contact(email="contact@example.com"),
        license=openapi.License(name="BSD License"),
    ),
    public=True,
)

urlpatterns = [
    # API documentation
    re_path(r'^swagger(?P<format>\.json|\.yaml)$', schema_view.without_ui(cache_timeout=0), name='schema-json'),
    re_path(r'^swagger/$', schema_view.with_ui('swagger', cache_timeout=0), name='schema-swagger-ui'),
    re_path(r'^redoc/$', schema_view.with_ui('redoc', cache_timeout=0), name='schema-redoc'),
    
    # API routes
    path('', include(router.urls)),
    path("parse/summary/", ParseSummaryView.as_view(), name="parse-summary"),
]

# Serve media files in development
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
