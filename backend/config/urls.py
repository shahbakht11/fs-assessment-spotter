from django.conf import settings
from django.http import FileResponse, Http404
from django.urls import path, re_path
from django.views.static import serve

from planner import views

urlpatterns = [
    path("api/health", views.health),
    path("api/geocode", views.geocode_view),
    path("api/plan", views.plan_view),
    path("api/heatmap", views.heatmap_view),
]


def spa_index(request, path=""):
    dist = settings.FRONTEND_DIST.resolve()
    candidate = (dist / path).resolve()
    if path and candidate.is_file() and candidate.is_relative_to(dist):  # e.g. /truck.svg
        return serve(request, path, document_root=dist)
    index = dist / "index.html"
    if not index.exists():
        raise Http404("Frontend not built. Run `npm run build` in frontend/ or use the Vite dev server.")
    return FileResponse(index.open("rb"), content_type="text/html")


# Single-process deployments (Docker/Render) serve the built React app from Django.
# On Vercel the static build is served by the CDN and only /api/* reaches Django.
urlpatterns += [
    re_path(r"^assets/(?P<path>.*)$", serve, {"document_root": settings.FRONTEND_DIST / "assets"}),
    re_path(r"^(?!api/)(?P<path>.*)$", spa_index),
]
