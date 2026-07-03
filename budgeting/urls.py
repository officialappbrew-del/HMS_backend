from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    BudgetViewSet,
    ForecastViewSet,
    GrantViewSet,
    BudgetVarianceViewSet,
    BudgetReportViewSet,
)

router = DefaultRouter()
router.register(r'budgets', BudgetViewSet)
router.register(r'forecasts', ForecastViewSet)
router.register(r'grants', GrantViewSet)
router.register(r'variances', BudgetVarianceViewSet)
router.register(r'reports', BudgetReportViewSet)

urlpatterns = [
    path('', include(router.urls)),
]
