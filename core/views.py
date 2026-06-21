from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.utils import timezone
from .models import (
    Country, State, LGA, FacilityType, Specialization,
    Language, SystemSetting, AuditLog
)
from .serializers import (
    CountrySerializer, StateSerializer, LGASerializer,
    FacilityTypeSerializer, SpecializationSerializer,
    LanguageSerializer, SystemSettingSerializer, AuditLogSerializer
)
from .permissions import IsSystemAdmin


class CountryViewSet(viewsets.ModelViewSet):
    queryset = Country.objects.filter(is_active=True)
    serializer_class = CountrySerializer
    permission_classes = [IsAuthenticated]
    
    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsSystemAdmin()]
        return super().get_permissions()


class StateViewSet(viewsets.ModelViewSet):
    serializer_class = StateSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        country_id = self.request.query_params.get('country_id')
        if country_id:
            return State.objects.filter(country_id=country_id)
        return State.objects.all()
    
    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsSystemAdmin()]
        return super().get_permissions()


class LGAViewSet(viewsets.ModelViewSet):
    serializer_class = LGASerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        state_id = self.request.query_params.get('state_id')
        if state_id:
            return LGA.objects.filter(state_id=state_id)
        return LGA.objects.all()
    
    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsSystemAdmin()]
        return super().get_permissions()


class FacilityTypeViewSet(viewsets.ModelViewSet):
    queryset = FacilityType.objects.all()
    serializer_class = FacilityTypeSerializer
    permission_classes = [IsAuthenticated]
    
    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsSystemAdmin()]
        return super().get_permissions()


class SpecializationViewSet(viewsets.ModelViewSet):
    queryset = Specialization.objects.all()
    serializer_class = SpecializationSerializer
    permission_classes = [IsAuthenticated]
    
    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsSystemAdmin()]
        return super().get_permissions()


class LanguageViewSet(viewsets.ModelViewSet):
    queryset = Language.objects.filter(is_active=True)
    serializer_class = LanguageSerializer
    permission_classes = [IsAuthenticated]
    
    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsSystemAdmin()]
        return super().get_permissions()


class SystemSettingViewSet(viewsets.ModelViewSet):
    queryset = SystemSetting.objects.all()
    serializer_class = SystemSettingSerializer
    permission_classes = [IsSystemAdmin]
    
    @action(detail=False, methods=['get'])
    def by_category(self, request):
        category = request.query_params.get('category', 'general')
        settings = SystemSetting.objects.filter(category=category)
        serializer = self.get_serializer(settings, many=True)
        return Response(serializer.data)


class AuditLogViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = AuditLogSerializer
    permission_classes = [IsSystemAdmin]
    
    def get_queryset(self):
        queryset = AuditLog.objects.all()
        
        # Filter by date range
        start_date = self.request.query_params.get('start_date')
        end_date = self.request.query_params.get('end_date')
        if start_date and end_date:
            queryset = queryset.filter(
                timestamp__date__gte=start_date,
                timestamp__date__lte=end_date
            )
        
        # Filter by action
        action = self.request.query_params.get('action')
        if action:
            queryset = queryset.filter(action__icontains=action)
        
        # Filter by resource type
        resource_type = self.request.query_params.get('resource_type')
        if resource_type:
            queryset = queryset.filter(resource_type=resource_type)
        
        # Filter by user
        user_id = self.request.query_params.get('user_id')
        if user_id:
            queryset = queryset.filter(user_id=user_id)
        
        return queryset
    
    @action(detail=False, methods=['get'])
    def summary(self, request):
        """Get audit log summary statistics."""
        total_logs = AuditLog.objects.count()
        today_logs = AuditLog.objects.filter(
            timestamp__date=timezone.now().date()
        ).count()
        
        # Count by action
        actions = AuditLog.objects.values('action').annotate(
            count=models.Count('id')
        ).order_by('-count')[:10]
        
        # Count by resource type
        resource_types = AuditLog.objects.values('resource_type').annotate(
            count=models.Count('id')
        ).order_by('-count')[:10]
        
        return Response({
            'total_logs': total_logs,
            'today_logs': today_logs,
            'top_actions': list(actions),
            'top_resource_types': list(resource_types),
        })