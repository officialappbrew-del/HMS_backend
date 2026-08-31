import csv
import threading
import logging
from rest_framework import viewsets, status, permissions, mixins, filters
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.authentication import BaseAuthentication
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.pagination import PageNumberPagination
from django.shortcuts import get_object_or_404
from django.db import transaction
from django.db import IntegrityError
from django.db.models import Count, Sum, Q
from django.contrib.auth.password_validation import validate_password
from django.contrib.auth.hashers import make_password
from django.core.validators import validate_email
from django.utils import timezone
from django.conf import settings
from rest_framework.parsers import JSONParser, MultiPartParser, FormParser
from rest_framework import serializers

from .models import (
    Tenant, SubscriptionPlan, TenantUser, Department,
    TenantSetting, TenantModule, TenantInvitation,
    TenantActivityLog, TenantBackup, BulkTenantUserUpload,
    CommunicationProfile, ExternalServiceProfile, SupportTicket, TenantDomain,
    SubscriptionPayment
)
from .serializers import (
    TenantSerializer, SubscriptionPlanSerializer, TenantUserSerializer,
    DepartmentSerializer, TenantSettingSerializer, TenantModuleSerializer,
    TenantInvitationSerializer, AcceptInvitationSerializer,
    TenantActivityLogSerializer, TenantBackupSerializer, TenantSummarySerializer,
    BulkTenantUserUploadSerializer, CommunicationProfileSerializer, ExternalServiceProfileSerializer,
    _check_employee_id_globally_unique, SelfSignupSerializer,
)
from core.permissions import IsSystemAdmin, IsTenantRootAdminOrGlobalAdmin
from core.models import AuditLog, SystemSetting, Country, FacilityType
from users.serializers import PasswordChangeSerializer
from superadmin.serializers import SupportTicketSerializer

import uuid
import json
import hmac
import hashlib
import datetime
import urllib.request
import urllib.error
import requests
from django.core.signing import dumps as signed_dumps, loads as signed_loads, BadSignature, SignatureExpired
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator


from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated, IsAdminUser
from rest_framework.response import Response

logger = logging.getLogger(__name__)
from rest_framework import status
from django.db import connection
from core.payment_settings import get_payment_setting, payment_setting_configured


class StandardPagination(PageNumberPagination):
    page_size = 25
    page_size_query_param = 'page_size'
    max_page_size = 50


# Public endpoint for listing active tenants (for login page)
class PublicTenantListView(APIView):
    """Public endpoint to list active tenants for login page."""
    permission_classes = [permissions.AllowAny]
    authentication_classes = []  # No authentication required
    
    def get(self, request):
        # Reset to public schema before querying
        from django.db import connection
        connection.set_schema('public')
        
        tenants = Tenant.objects.filter(
            subscription_status__in=['active', 'trial']
        ).only('public_id', 'name', 'code', 'domain', 'logo')
        
        data = [
            {
                'public_id': str(t.public_id),
                'name': t.name,
                'code': t.code,
                'domain': t.domain,
            }
            for t in tenants
        ]
        return Response(data)



# class TenantViewSet(viewsets.ModelViewSet):
#     """ViewSet for managing tenants (global admin only)."""
#     queryset = Tenant.objects.all()
#     serializer_class = TenantSerializer
#     pagination_class = StandardPagination
#     permission_classes = [IsSystemAdmin]
#     lookup_field = 'public_id'
    
#     def get_queryset(self):
#         user = self.request.user
        
#         # Filter by subscription status
#         status_filter = self.request.query_params.get('status')
#         if status_filter:
#             self.queryset = self.queryset.filter(subscription_status=status_filter)
        
#         # Filter by NHIS accreditation
#         nhis_filter = self.request.query_params.get('nhis_accreditation')
#         if nhis_filter:
#             self.queryset = self.queryset.filter(nhis_accreditation=nhis_filter)
        
#         # Search by name, code, or domain
#         search = self.request.query_params.get('search')
#         if search:
#             self.queryset = self.queryset.filter(
#                 Q(name__icontains=search) |
#                 Q(code__icontains=search) |
#                 Q(domain__icontains=search) |
#                 Q(email__icontains=search)
#             )
        
#         return self.queryset
    
#     def perform_create(self, serializer):
#         with transaction.atomic():
#             # Create tenant
#             tenant = serializer.save()

#             # Convert serializer data to JSON-safe values for audit logging
#             audit_payload = serializer.data.copy()
#             for key, value in audit_payload.items():
#                 if hasattr(value, 'isoformat') and callable(value.isoformat):
#                     audit_payload[key] = value.isoformat()
#                 elif isinstance(value, list):
#                     audit_payload[key] = [
#                         item.isoformat() if hasattr(item, 'isoformat') and callable(item.isoformat) else item
#                         for item in value
#                     ]
#                 elif isinstance(value, dict):
#                     audit_payload[key] = {
#                         inner_key: (
#                             inner_value.isoformat()
#                             if hasattr(inner_value, 'isoformat') and callable(inner_value.isoformat)
#                             else inner_value
#                         )
#                         for inner_key, inner_value in value.items()
#                     }
            
#             # Create audit log
#             AuditLog.objects.create(
#                 user=self.request.user,
#                 action='create_tenant',
#                 resource_type='tenant',
#                 resource_id=str(tenant.id),
#                 new_values=audit_payload
#             )
            
#             # Create initial admin user
#             admin_data = {
#                 'username': f"admin@{tenant.domain.split('.')[0]}",
#                 'email': tenant.email,
#                 'first_name': 'Admin',
#                 'last_name': tenant.name,
#                 'role': 'admin',
#                 'password': 'TempPass123!',
#                 'is_staff': True,
#             }
            
#             admin_user = TenantUser.objects.create(
#                 tenant=tenant,
#                 **admin_data
#             )
#             admin_user.set_password(admin_data['password'])
#             admin_user.save()
    
#     def perform_update(self, serializer):
#         old_tenant = self.get_object()
#         old_data = TenantSerializer(old_tenant).data
        
#         tenant = serializer.save()
        
#         # Log the action
#         AuditLog.objects.create(
#             user=self.request.user,
#             action='update_tenant',
#             resource_type='tenant',
#             resource_id=str(tenant.id),
#             old_values=old_data,
#             new_values=serializer.data
#         )
    
#     def perform_destroy(self, instance):
#         tenant_id = instance.id
#         tenant_name = instance.name
        
#         # Log before deletion
#         AuditLog.objects.create(
#             user=self.request.user,
#             action='delete_tenant',
#             resource_type='tenant',
#             resource_id=str(tenant_id),
#             old_values={'name': tenant_name}
#         )
        
#         instance.delete()
    
#     @action(detail=True, methods=['post'])
#     def suspend(self, request, pk=None):
#         """Suspend a tenant."""
#         tenant = self.get_object()
#         tenant.subscription_status = Tenant.SubscriptionStatus.SUSPENDED
#         tenant.is_active = False
#         tenant.save()
        
#         # Log action
#         AuditLog.objects.create(
#             user=request.user,
#             action='suspend_tenant',
#             resource_type='tenant',
#             resource_id=str(tenant.id),
#             new_values={'subscription_status': 'suspended', 'is_active': False}
#         )
        
#         return Response({'detail': 'Tenant suspended successfully'})
    
#     @action(detail=True, methods=['post'])
#     def activate(self, request, pk=None):
#         """Activate a tenant."""
#         tenant = self.get_object()
#         tenant.subscription_status = Tenant.SubscriptionStatus.ACTIVE
#         tenant.is_active = True
#         tenant.save()
        
#         # Log action
#         AuditLog.objects.create(
#             user=request.user,
#             action='activate_tenant',
#             resource_type='tenant',
#             resource_id=str(tenant.id),
#             new_values={'subscription_status': 'active', 'is_active': True}
#         )
        
#         return Response({'detail': 'Tenant activated successfully'})
    
#     @action(detail=True, methods=['post'])
#     def cancel(self, request, pk=None):
#         """Cancel tenant subscription."""
#         tenant = self.get_object()
#         tenant.subscription_status = Tenant.SubscriptionStatus.CANCELLED
#         tenant.is_active = False
#         tenant.save()
        
#         # Log action
#         AuditLog.objects.create(
#             user=request.user,
#             action='cancel_tenant',
#             resource_type='tenant',
#             resource_id=str(tenant.id),
#             new_values={'subscription_status': 'cancelled', 'is_active': False}
#         )
        
#         return Response({'detail': 'Tenant subscription cancelled'})
    
#     @action(detail=True, methods=['get'])
#     def summary(self, request, pk=None):
#         """Get tenant summary statistics."""
#         tenant = self.get_object()
        
#         # Get statistics
#         user_count = TenantUser.objects.filter(tenant=tenant).count()
#         # patient_count = Patient.objects.filter(tenant=tenant).count()  # Will be added later
#         patient_count = 0
#         department_count = Department.objects.filter(tenant=tenant).count()
#         active_modules_count = TenantModule.objects.filter(
#             tenant=tenant, is_enabled=True
#         ).count()
        
#         # Get last backup
#         last_backup = TenantBackup.objects.filter(
#             tenant=tenant,
#             status=TenantBackup.BackupStatus.COMPLETED
#         ).order_by('-created_at').first()
        
#         data = {
#             'public_id': str(tenant.public_id),
#             'name': tenant.name,
#             'code': tenant.code,
#             'domain': tenant.domain,
#             'subscription_status': tenant.subscription_status,
#             'subscription_plan': tenant.subscription_plan.id if tenant.subscription_plan else None,
#             'user_count': user_count,
#             'patient_count': patient_count,
#             'department_count': department_count,
#             'active_modules_count': active_modules_count,
#             'storage_used_mb': 0,  # Will be calculated from storage
#             'last_backup_time': last_backup.created_at if last_backup else None,
#         }
        
#         serializer = TenantSummarySerializer(data=data)
#         serializer.is_valid()
#         return Response(serializer.data)
    
#     @action(detail=False, methods=['get'])
#     def statistics(self, request):
#         """Get global tenant statistics."""
#         total_tenants = Tenant.objects.count()
#         active_tenants = Tenant.objects.filter(
#             subscription_status=Tenant.SubscriptionStatus.ACTIVE,
#             is_active=True
#         ).count()
#         trial_tenants = Tenant.objects.filter(
#             subscription_status=Tenant.SubscriptionStatus.TRIAL
#         ).count()
#         suspended_tenants = Tenant.objects.filter(
#             subscription_status=Tenant.SubscriptionStatus.SUSPENDED
#         ).count()
        
#         # Monthly revenue projection
#         active_tenants_revenue = Tenant.objects.filter(
#             subscription_status=Tenant.SubscriptionStatus.ACTIVE
#         ).aggregate(total=Sum('monthly_fee'))['total'] or 0
        
#         # Tenants by facility type
#         tenants_by_type = Tenant.objects.values(
#             'facility_type__name'
#         ).annotate(
#             count=Count('id')
#         ).order_by('-count')
        
#         # Tenants by state
#         tenants_by_state = Tenant.objects.values(
#             'state__name'
#         ).annotate(
#             count=Count('id')
#         ).order_by('-count')
        
#         return Response({
#             'total_tenants': total_tenants,
#             'active_tenants': active_tenants,
#             'trial_tenants': trial_tenants,
#             'suspended_tenants': suspended_tenants,
#             'monthly_revenue': float(active_tenants_revenue),
#             'tenants_by_facility_type': list(tenants_by_type),
#             'tenants_by_state': list(tenants_by_state),
#         })

class TenantViewSet(viewsets.ModelViewSet):
    """ViewSet for managing tenants (global admin only)."""
    queryset = Tenant.objects.all()
    serializer_class = TenantSerializer
    pagination_class = StandardPagination
    permission_classes = [IsSystemAdmin]
    lookup_field = 'public_id'
    
    def get_queryset(self):
        user = self.request.user
        
        # Filter by subscription status
        status_filter = self.request.query_params.get('status')
        if status_filter:
            self.queryset = self.queryset.filter(subscription_status=status_filter)
        
        # Filter by NHIS accreditation
        nhis_filter = self.request.query_params.get('nhis_accreditation')
        if nhis_filter:
            self.queryset = self.queryset.filter(nhis_accreditation=nhis_filter)
        
        # Search by name, code, or domain
        search = self.request.query_params.get('search')
        if search:
            self.queryset = self.queryset.filter(
                Q(name__icontains=search) |
                Q(code__icontains=search) |
                Q(domain__icontains=search) |
                Q(email__icontains=search)
            )
        
        return self.queryset
    
    def perform_create(self, serializer):
        with transaction.atomic():
            # Create tenant
            tenant = serializer.save()

            # Convert serializer data to JSON-safe values for audit logging
            audit_payload = serializer.data.copy()
            for key, value in audit_payload.items():
                if hasattr(value, 'isoformat') and callable(value.isoformat):
                    audit_payload[key] = value.isoformat()
                elif isinstance(value, list):
                    audit_payload[key] = [
                        item.isoformat() if hasattr(item, 'isoformat') and callable(item.isoformat) else item
                        for item in value
                    ]
                elif isinstance(value, dict):
                    audit_payload[key] = {
                        inner_key: (
                            inner_value.isoformat()
                            if hasattr(inner_value, 'isoformat') and callable(inner_value.isoformat)
                            else inner_value
                        )
                        for inner_key, inner_value in value.items()
                    }
            
            # Create audit log
            AuditLog.objects.create(
                user=self.request.user,
                action='create_tenant',
                resource_type='tenant',
                resource_id=str(tenant.id),
                new_values=audit_payload
            )

            root_admin_data = getattr(serializer, 'root_admin_data', None)
            if root_admin_data:
                # Create tenant root admin
                root_username = root_admin_data.get('username') or f"{root_admin_data['first_name'].lower()}.{root_admin_data['last_name'].lower()}".replace(' ', '_')
                unique_username = root_username
                counter = 1
                while TenantUser.objects.filter(tenant=tenant, username=unique_username).exists():
                    unique_username = f"{root_username}{counter}"
                    counter += 1

                if TenantUser.objects.filter(tenant=tenant, email=root_admin_data['email']).exists():
                    raise serializers.ValidationError({'root_admin.email': ['A user with this email already exists for this tenant.']})

                candidate_employee_id = root_admin_data.get('employee_id') or root_admin_data.get('user_id')
                if candidate_employee_id:
                    global_conflict = _check_employee_id_globally_unique(candidate_employee_id, exclude_tenant=tenant)
                    if global_conflict:
                        raise serializers.ValidationError({
                            'root_admin.employee_id': [
                                f"Employee ID '{candidate_employee_id}' is already used in tenant '{global_conflict.name}' ({global_conflict.domain})."
                            ]
                        })

                admin_user = TenantUser.objects.create(
                    tenant=tenant,
                    username=unique_username,
                    email=root_admin_data['email'],
                    first_name=root_admin_data['first_name'],
                    last_name=root_admin_data['last_name'],
                    phone=root_admin_data.get('phone', ''),
                    role='admin',
                    employee_id=root_admin_data.get('employee_id') or root_admin_data.get('user_id') or None,
                    is_staff=True,
                    is_active=True,
                    is_root_admin=True,
                )
                admin_user.set_password(root_admin_data['password'])
                admin_user.save()

                AuditLog.objects.create(
                    user=self.request.user,
                    action='create_root_admin',
                    resource_type='tenant_user',
                    resource_id=str(admin_user.id),
                    new_values={
                        'email': admin_user.email,
                        'tenant': str(tenant.public_id),
                        'is_root_admin': True,
                    }
                )
            # else:
            #     admin_data = {
            #         'username': f"admin@{tenant.domain.split('.')[0]}",
            #         'email': tenant.email,
            #         'first_name': 'Admin',
            #         'last_name': tenant.name,
            #         'role': 'admin',
            #         'password': 'TempPass123!',
            #         'is_staff': True,
            #     }

            #     try:
            #         connection.set_schema(tenant.schema_name)
            #         admin_user = TenantUser.objects.create(
            #             tenant=tenant,
            #             **admin_data
            #         )
            #         admin_user.set_password(admin_data['password'])
            #         admin_user.save()
            #     finally:
            #         connection.set_schema('public')
    
    def perform_update(self, serializer):
        old_tenant = self.get_object()
        old_data = TenantSerializer(old_tenant).data
        
        tenant = serializer.save()
        
        # Log the action
        AuditLog.objects.create(
            user=self.request.user,
            action='update_tenant',
            resource_type='tenant',
            resource_id=str(tenant.id),
            old_values=old_data,
            new_values=serializer.data
        )
    
    def perform_destroy(self, instance):
        tenant_id = instance.id
        tenant_name = instance.name
        
        # Log before deletion
        AuditLog.objects.create(
            user=self.request.user,
            action='delete_tenant',
            resource_type='tenant',
            resource_id=str(tenant_id),
            old_values={'name': tenant_name}
        )
        
        instance.delete()
    
    @action(detail=True, methods=['post'])
    def suspend(self, request, pk=None):
        """Suspend a tenant."""
        tenant = self.get_object()
        tenant.subscription_status = Tenant.SubscriptionStatus.SUSPENDED
        tenant.is_active = False
        tenant.save()
        
        # Log action
        AuditLog.objects.create(
            user=request.user,
            action='suspend_tenant',
            resource_type='tenant',
            resource_id=str(tenant.id),
            new_values={'subscription_status': 'suspended', 'is_active': False}
        )
        
        return Response({'detail': 'Tenant suspended successfully'})
    
    @action(detail=True, methods=['post'])
    def activate(self, request, pk=None):
        """Activate a tenant."""
        tenant = self.get_object()
        tenant.subscription_status = Tenant.SubscriptionStatus.ACTIVE
        tenant.is_active = True
        tenant.save()
        
        # Log action
        AuditLog.objects.create(
            user=request.user,
            action='activate_tenant',
            resource_type='tenant',
            resource_id=str(tenant.id),
            new_values={'subscription_status': 'active', 'is_active': True}
        )
        
        return Response({'detail': 'Tenant activated successfully'})
    
    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        """Cancel tenant subscription."""
        tenant = self.get_object()
        tenant.subscription_status = Tenant.SubscriptionStatus.CANCELLED
        tenant.is_active = False
        tenant.save()
        
        # Log action
        AuditLog.objects.create(
            user=request.user,
            action='cancel_tenant',
            resource_type='tenant',
            resource_id=str(tenant.id),
            new_values={'subscription_status': 'cancelled', 'is_active': False}
        )
        
        return Response({'detail': 'Tenant subscription cancelled'})
    
    @action(detail=True, methods=['get'])
    def summary(self, request, pk=None):
        """Get tenant summary statistics."""
        tenant = self.get_object()
        
        # Get statistics
        user_count = TenantUser.objects.filter(tenant=tenant).count()
        # patient_count = Patient.objects.filter(tenant=tenant).count()  # Will be added later
        patient_count = 0
        department_count = Department.objects.filter(tenant=tenant).count()
        active_modules_count = TenantModule.objects.filter(
            tenant=tenant, is_enabled=True
        ).count()
        
        # Get last backup
        last_backup = TenantBackup.objects.filter(
            tenant=tenant,
            status=TenantBackup.BackupStatus.COMPLETED
        ).order_by('-created_at').first()
        
        data = {
            'public_id': str(tenant.public_id),
            'name': tenant.name,
            'code': tenant.code,
            'domain': tenant.domain,
            'subscription_status': tenant.subscription_status,
            'subscription_plan': tenant.subscription_plan.id if tenant.subscription_plan else None,
            'user_count': user_count,
            'patient_count': patient_count,
            'department_count': department_count,
            'active_modules_count': active_modules_count,
            'storage_used_mb': 0,  # Will be calculated from storage
            'last_backup_time': last_backup.created_at if last_backup else None,
        }
        
        serializer = TenantSummarySerializer(data=data)
        serializer.is_valid()
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def statistics(self, request):
        """Get global tenant statistics."""
        total_tenants = Tenant.objects.count()
        active_tenants = Tenant.objects.filter(
            subscription_status=Tenant.SubscriptionStatus.ACTIVE,
            is_active=True
        ).count()
        trial_tenants = Tenant.objects.filter(
            subscription_status=Tenant.SubscriptionStatus.TRIAL
        ).count()
        suspended_tenants = Tenant.objects.filter(
            subscription_status=Tenant.SubscriptionStatus.SUSPENDED
        ).count()
        
        # Monthly revenue projection
        active_tenants_revenue = Tenant.objects.filter(
            subscription_status=Tenant.SubscriptionStatus.ACTIVE
        ).aggregate(total=Sum('monthly_fee'))['total'] or 0
        
        # Tenants by facility type
        tenants_by_type = Tenant.objects.values(
            'facility_type__name'
        ).annotate(
            count=Count('id')
        ).order_by('-count')
        
        # Tenants by state
        tenants_by_state = Tenant.objects.values(
            'state__name'
        ).annotate(
            count=Count('id')
        ).order_by('-count')
        
        return Response({
            'total_tenants': total_tenants,
            'active_tenants': active_tenants,
            'trial_tenants': trial_tenants,
            'suspended_tenants': suspended_tenants,
            'monthly_revenue': float(active_tenants_revenue),
            'tenants_by_facility_type': list(tenants_by_type),
            'tenants_by_state': list(tenants_by_state),
        })
    
    @action(detail=True, methods=['get'], url_path='admins')
    def get_admins(self, request, public_id=None):
        """
        Get all admin users for a specific tenant.
        URL: /api/v1/tenants/<tenant_id>/admins/
        
        Query params:
        - search: Search by name, email, or username
        - is_active: Filter by active status (true/false)
        - page: Page number
        - page_size: Items per page
        """
        tenant = self.get_object()
        
        # Base queryset - get all admin users for this tenant
        admin_users = TenantUser.objects.filter(
            tenant=tenant,
            role='admin'
        ).select_related('tenant', 'department', 'state')
        
        # Filter by search term
        search = request.query_params.get('search')
        if search:
            admin_users = admin_users.filter(
                Q(first_name__icontains=search) |
                Q(last_name__icontains=search) |
                Q(email__icontains=search) |
                Q(username__icontains=search) |
                Q(employee_id__icontains=search)
            )
        
        # Filter by active status
        is_active = request.query_params.get('is_active')
        if is_active is not None:
            if is_active.lower() == 'true':
                admin_users = admin_users.filter(is_active=True)
            elif is_active.lower() == 'false':
                admin_users = admin_users.filter(is_active=False)
        
        # Order by name
        admin_users = admin_users.order_by('first_name', 'last_name')
        
        # Pagination
        paginator = StandardPagination()
        paginated_admins = paginator.paginate_queryset(admin_users, request)
        
        # Serialize
        serializer = TenantUserSerializer(paginated_admins, many=True)
        
        # Return paginated response with tenant info
        response = paginator.get_paginated_response(serializer.data)
        
        # Add tenant info to the response
        response.data['tenant'] = {
            'public_id': str(tenant.public_id),
            'name': tenant.name,
            'code': tenant.code,
            'domain': tenant.domain,
            'subscription_status': tenant.subscription_status
        }
        
        return response

# @api_view(['POST'])
# @permission_classes([IsAuthenticated, IsSystemAdmin])
# def create_tenant_admin(request, tenant_id):
#     try:
#         tenant = Tenant.objects.get(public_id=tenant_id)
#     except Tenant.DoesNotExist:
#         return Response(
#             {'error': 'Tenant not found.'},
#             status=status.HTTP_404_NOT_FOUND,
#         )

#     # Fix: Parse data if it's a string (when Content-Type header is missing)
#     data = request.data
#     if isinstance(data, str):
#         try:
#             import json
#             data = json.loads(data)
#         except json.JSONDecodeError:
#             return Response(
#                 {'error': 'Invalid JSON data. Please check your request body.'},
#                 status=status.HTTP_400_BAD_REQUEST,
#             )
    
#     email = data.get('email')
#     password = data.get('password')
#     first_name = (data.get('first_name') or '').strip()
#     last_name = (data.get('last_name') or '').strip()

#     if not email or not password or not first_name or not last_name:
#         return Response(
#             {
#                 'error': 'email, password, first_name, and last_name are required.'
#             },
#             status=status.HTTP_400_BAD_REQUEST,
#         )

#     try:
#         validate_email(email)
#     except Exception:
#         return Response(
#             {'error': 'Invalid email format.'},
#             status=status.HTTP_400_BAD_REQUEST,
#         )

#     try:
#         validate_password(password)
#     except Exception as exc:
#         return Response(
#             {'error': exc.messages},
#             status=status.HTTP_400_BAD_REQUEST,
#         )

#     supplied_username = (data.get('username') or '').strip()
#     if supplied_username:
#         username = supplied_username
#     else:
#         base_username = f"{first_name.lower()}.{last_name.lower()}".replace(' ', '_')
#         username = base_username

#     counter = 1
#     original_username = username
#     while TenantUser.objects.filter(tenant=tenant, username=username).exists():
#         username = f"{original_username}{counter}"
#         counter += 1

#     try:
#         admin_user = TenantUser.objects.create(
#             tenant=tenant,
#             username=username,
#             email=email,
#             first_name=first_name,
#             last_name=last_name,
#             phone=data.get('phone', ''),
#             role='admin',
#             employee_id=data.get('employee_id') or data.get('user_id') or None,
#             is_staff=True,
#             is_active=True
#         )
#     except IntegrityError:
#         return Response(
#             {'error': f'A user with email ({email}) already exists. Please use a different email address.'},
#             status=status.HTTP_400_BAD_REQUEST,
#         )
#     admin_user.set_password(password)
#     admin_user.save()
#     admin_user.refresh_from_db()

#     return Response(
#         {
#             'message': 'Tenant admin created successfully',
#             'user': {
#                 'id': admin_user.id,
#                 'user_id': admin_user.employee_id,
#                 'username': admin_user.username,
#                 'email': admin_user.email,
#                 'tenant_public_id': str(tenant.public_id),
#                 'tenant_name': tenant.name,
#             },
#         },
#         status=status.HTTP_201_CREATED,
#     )

@api_view(['POST'])
@permission_classes([IsAuthenticated, IsSystemAdmin])
def create_tenant_admin(request, tenant_id):
    try:
        tenant = Tenant.objects.get(public_id=tenant_id)
    except Tenant.DoesNotExist:
        return Response(
            {'error': 'Tenant not found.'},
            status=status.HTTP_404_NOT_FOUND,
        )

    # Parse data
    data = request.data
    if isinstance(data, str):
        try:
            import json
            data = json.loads(data)
        except json.JSONDecodeError:
            return Response(
                {'error': 'Invalid JSON data.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
    
    email = data.get('email')
    password = data.get('password')
    first_name = (data.get('first_name') or '').strip()
    last_name = (data.get('last_name') or '').strip()

    if not email or not password or not first_name or not last_name:
        return Response(
            {
                'error': 'email, password, first_name, and last_name are required.'
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    if data.get('is_root_admin'):
        return Response(
            {
                'error': 'Root admin creation is not supported on this endpoint. Use /create-root-admin/ or include root_admin when creating the tenant.'
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    # Email validation
    try:
        validate_email(email)
    except Exception:
        return Response(
            {'error': 'Invalid email format.'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # Password validation
    try:
        validate_password(password)
    except Exception as exc:
        return Response(
            {'error': exc.messages},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # Username generation
    supplied_username = (data.get('username') or '').strip()
    if supplied_username:
        username = supplied_username
    else:
        base_username = f"{first_name.lower()}.{last_name.lower()}".replace(' ', '_')
        username = base_username

    counter = 1
    original_username = username
    while TenantUser.objects.filter(tenant=tenant, username=username).exists():
        username = f"{original_username}{counter}"
        counter += 1

    # Employee ID handling
    employee_id = data.get('employee_id') or data.get('user_id') or None
    
    # Check if employee_id exists globally across tenants
    if employee_id:
        conflicting = _check_employee_id_globally_unique(employee_id, exclude_tenant=tenant)
        if conflicting:
            return Response(
                {
                    'error': 'Employee ID already exists globally.',
                    'code': 'DUPLICATE_EMPLOYEE_ID_GLOBAL',
                    'details': f'The employee ID "{employee_id}" is already assigned to another tenant user.',
                    'suggestion': 'Please use a different employee ID or leave it blank.'
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
    
    # Check if email exists
    if TenantUser.objects.filter(tenant=tenant, email=email).exists():
        return Response(
            {
                'error': 'Email already exists.',
                'code': 'DUPLICATE_EMAIL',
                'details': f'A user with email "{email}" already exists.',
                'suggestion': 'Please use a different email address.'
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    # Create user
    try:
        admin_user = TenantUser.objects.create(
            tenant=tenant,
            username=username,
            email=email,
            first_name=first_name,
            last_name=last_name,
            phone=data.get('phone', ''),
            role='admin',
            employee_id=employee_id,
            is_staff=True,
            is_active=True,
            is_root_admin=bool(data.get('is_root_admin', False))
        )
    except IntegrityError as e:
        error_msg = str(e)
        
        if 'employee_id' in error_msg.lower():
            return Response(
                {
                    'error': 'Employee ID already exists.',
                    'code': 'DUPLICATE_EMPLOYEE_ID',
                    'details': f'The employee ID "{employee_id}" is already in use.',
                    'suggestion': 'Please use a different employee ID.'
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        elif 'email' in error_msg.lower():
            return Response(
                {
                    'error': 'Email already exists.',
                    'code': 'DUPLICATE_EMAIL',
                    'details': f'Email "{email}" is already registered.',
                    'suggestion': 'Please use a different email.'
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        elif 'username' in error_msg.lower():
            return Response(
                {
                    'error': 'Username already exists.',
                    'code': 'DUPLICATE_USERNAME',
                    'details': f'Username "{username}" is already taken.',
                    'suggestion': 'Please use a different username.'
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        else:
            return Response(
                {
                    'error': 'Database integrity error.',
                    'code': 'INTEGRITY_ERROR',
                    'details': error_msg
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
    
    admin_user.set_password(password)
    admin_user.save()
    admin_user.refresh_from_db()

    return Response(
        {
            'message': 'Tenant admin created successfully',
            'user': {
                'id': admin_user.id,
                'user_id': admin_user.employee_id,
                'username': admin_user.username,
                'email': admin_user.email,
                'tenant_public_id': str(tenant.public_id),
                'tenant_name': tenant.name,
            },
        },
        status=status.HTTP_201_CREATED,
    )


@api_view(['POST'])
@permission_classes([IsAuthenticated, IsSystemAdmin])
def create_tenant_root_admin(request, tenant_id):
    try:
        tenant = Tenant.objects.get(public_id=tenant_id)
    except Tenant.DoesNotExist:
        return Response(
            {'error': 'Tenant not found.'},
            status=status.HTTP_404_NOT_FOUND,
        )

    data = request.data
    if isinstance(data, str):
        try:
            import json
            data = json.loads(data)
        except json.JSONDecodeError:
            return Response(
                {'error': 'Invalid JSON data.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

    email = data.get('email')
    password = data.get('password')
    first_name = (data.get('first_name') or '').strip()
    last_name = (data.get('last_name') or '').strip()

    if not email or not password or not first_name or not last_name:
        return Response(
            {
                'error': 'email, password, first_name, and last_name are required.'
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        validate_email(email)
    except Exception:
        return Response(
            {'error': 'Invalid email format.'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        validate_password(password)
    except Exception as exc:
        return Response(
            {'error': exc.messages},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if TenantUser.objects.filter(tenant=tenant, is_root_admin=True).exists():
        return Response(
            {'error': 'A root admin already exists for this tenant.'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    supplied_username = (data.get('username') or '').strip()
    if supplied_username:
        username = supplied_username
    else:
        base_username = f"{first_name.lower()}.{last_name.lower()}".replace(' ', '_')
        username = base_username

    counter = 1
    original_username = username
    while TenantUser.objects.filter(tenant=tenant, username=username).exists():
        username = f"{original_username}{counter}"
        counter += 1

    employee_id = data.get('employee_id') or data.get('user_id') or None
    if employee_id:
        conflicting = _check_employee_id_globally_unique(employee_id, exclude_tenant=tenant)
        if conflicting:
            return Response(
                {
                    'error': 'Employee ID already exists globally.',
                    'code': 'DUPLICATE_EMPLOYEE_ID_GLOBAL',
                    'details': f'The employee ID "{employee_id}" is already assigned to another tenant user.',
                    'suggestion': 'Please use a different employee ID or leave it blank.'
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

    if TenantUser.objects.filter(tenant=tenant, email=email).exists():
        return Response(
            {
                'error': 'Email already exists.',
                'code': 'DUPLICATE_EMAIL',
                'details': f'A user with email "{email}" already exists.',
                'suggestion': 'Please use a different email address.'
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        admin_user = TenantUser.objects.create(
            tenant=tenant,
            username=username,
            email=email,
            first_name=first_name,
            last_name=last_name,
            phone=data.get('phone', ''),
            role='admin',
            employee_id=employee_id,
            is_staff=True,
            is_active=True,
            is_root_admin=True,
        )
    except IntegrityError as e:
        error_msg = str(e)
        if 'employee_id' in error_msg.lower():
            return Response(
                {
                    'error': 'Employee ID already exists.',
                    'code': 'DUPLICATE_EMPLOYEE_ID',
                    'details': f'The employee ID "{employee_id}" is already in use.',
                    'suggestion': 'Please use a different employee ID.'
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        elif 'email' in error_msg.lower():
            return Response(
                {
                    'error': 'Email already exists.',
                    'code': 'DUPLICATE_EMAIL',
                    'details': f'Email "{email}" is already registered.',
                    'suggestion': 'Please use a different email.'
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        elif 'username' in error_msg.lower():
            return Response(
                {
                    'error': 'Username already exists.',
                    'code': 'DUPLICATE_USERNAME',
                    'details': f'Username "{username}" is already taken.',
                    'suggestion': 'Please use a different username.'
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        else:
            return Response(
                {
                    'error': 'Database integrity error.',
                    'code': 'INTEGRITY_ERROR',
                    'details': error_msg
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

    admin_user.set_password(password)
    admin_user.save()
    admin_user.refresh_from_db()

    return Response(
        {
            'message': 'Tenant root admin created successfully',
            'user': {
                'id': admin_user.id,
                'user_id': admin_user.employee_id,
                'username': admin_user.username,
                'email': admin_user.email,
                'tenant_public_id': str(tenant.public_id),
                'tenant_name': tenant.name,
                'is_root_admin': admin_user.is_root_admin,
            },
        },
        status=status.HTTP_201_CREATED,
    )


@api_view(['GET'])
@permission_classes([IsAuthenticated, IsSystemAdmin])
def get_tenant_admins(request, tenant_id):
    """
    Get all admin users for a specific tenant.
    URL: /api/v1/tenants/tenants/<tenant_id>/admins/
    """
    try:
        tenant = Tenant.objects.get(public_id=tenant_id)
    except Tenant.DoesNotExist:
        return Response(
            {'error': 'Tenant not found.'},
            status=status.HTTP_404_NOT_FOUND,
        )
    
    # Get all admin users for this tenant
    admin_users = TenantUser.objects.filter(
        tenant=tenant,
        role='admin'
    ).select_related('tenant', 'department')
    
    # Pagination (optional)
    paginator = StandardPagination()
    paginated_admins = paginator.paginate_queryset(admin_users, request)
    
    # Serialize the data
    serializer = TenantUserSerializer(paginated_admins, many=True)
    
    return paginator.get_paginated_response(serializer.data)

    
class SubscriptionPlanViewSet(viewsets.ModelViewSet):
    """ViewSet for managing subscription plans."""
    queryset = SubscriptionPlan.objects.all()
    serializer_class = SubscriptionPlanSerializer
    pagination_class = StandardPagination
    permission_classes = [IsSystemAdmin]

    def get_permissions(self):
        if self.request.method in permissions.SAFE_METHODS:
            return [permissions.AllowAny()]
        return super().get_permissions()
    
    def perform_create(self, serializer):
        plan = serializer.save()
        
        # Log action
        AuditLog.objects.create(
            user=self.request.user,
            action='create_subscription_plan',
            resource_type='subscription_plan',
            resource_id=str(plan.id),
            new_values=serializer.data
        )
    
    def perform_update(self, serializer):
        old_plan = self.get_object()
        old_data = SubscriptionPlanSerializer(old_plan).data
        
        plan = serializer.save()
        
        # Log action
        AuditLog.objects.create(
            user=self.request.user,
            action='update_subscription_plan',
            resource_type='subscription_plan',
            resource_id=str(plan.id),
            old_values=old_data,
            new_values=serializer.data
        )
    
    def perform_destroy(self, instance):
        plan_id = instance.id
        plan_name = instance.name
        
        # Log before deletion
        AuditLog.objects.create(
            user=self.request.user,
            action='delete_subscription_plan',
            resource_type='subscription_plan',
            resource_id=str(plan_id),
            old_values={'name': plan_name}
        )
        
        instance.delete()
    
    @action(detail=True, methods=['post'])
    def set_default(self, request, pk=None):
        """Set a subscription plan as default."""
        plan = self.get_object()
        
        # Remove default from other plans
        SubscriptionPlan.objects.filter(is_default=True).update(is_default=False)
        
        # Set this plan as default
        plan.is_default = True
        plan.save()
        
        return Response({'detail': f'{plan.name} set as default plan'})


class TenantUserViewSet(viewsets.ModelViewSet):
    """ViewSet for managing tenant users."""
    serializer_class = TenantUserSerializer
    pagination_class = StandardPagination
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    ordering = ['first_name', 'last_name']
    search_fields = ['first_name', 'last_name', 'email', 'employee_id', 'phone', 'role', 'department__name', 'username']
    ordering_fields = ['first_name', 'last_name', 'email', 'role', 'employment_date', 'department', 'employment_status', 'username']

    def create(self, request, *args, **kwargs):
        temporary_password = request.data.get('password')
        send_credentials = str(request.data.get('send_credentials', '')).lower() in {
            '1', 'true', 'yes', 'on'
        }
        response = super().create(request, *args, **kwargs)
        if response.status_code >= 400:
            return response

        staff = self.get_queryset().filter(pk=response.data.get('id')).first()
        if not send_credentials:
            response.data['welcome_email_status'] = 'not_requested'
            return response

        if not staff or not temporary_password or not staff.email:
            response.data['welcome_email_status'] = 'not_queued'
            return response

        from users.tasks import send_tenant_welcome_email, send_tenant_welcome_email_task
        from tenants.communication import TenantEmailConfigurationError, resolve_email_identity
        try:
            resolve_email_identity(staff.tenant, allow_global_fallback=False)
        except TenantEmailConfigurationError:
            response.data['welcome_email_status'] = 'tenant_email_not_configured'
            response.data['welcome_email_error'] = 'The tenant has not configured complete email credentials. The account was created, but no email was sent.'
            return response

        login_url = f"{getattr(settings, 'FRONTEND_URL', '').rstrip('/')}/login"
        email_args = (
            staff.email,
            staff.get_full_name(),
            staff.tenant.name,
            temporary_password,
            login_url,
            staff.id,
        )
        try:
            send_tenant_welcome_email_task.delay(*email_args)
            response.data['welcome_email_status'] = 'queued'
        except Exception:
            logger.exception('Unable to queue welcome email for tenant user %s; using direct send', staff.pk)
            try:
                send_tenant_welcome_email(*email_args)
                response.data['welcome_email_status'] = 'sent'
            except Exception:
                logger.exception('Unable to send welcome email directly for tenant user %s', staff.pk)
                response.data['welcome_email_status'] = 'not_queued'

        response.data['credentials'] = {
            'employee_id': staff.employee_id or staff.username,
            'email': staff.email,
            'password': temporary_password,
        }
        return response

    def _is_request_root_admin(self):
        user = self.request.user
        if not user or not user.is_authenticated:
            return False

        if getattr(user, 'is_superuser', False):
            return True

        if getattr(user, 'role', None) in ['super_admin', 'system_admin']:
            return True

        tenant_user = getattr(user, 'tenant_user', None)
        return bool(tenant_user and getattr(tenant_user, 'is_root_admin', False))
    
    def _get_request_tenant_user(self):
        """Resolve the TenantUser instance associated with the current request."""
        user = self.request.user
        if hasattr(user, 'tenant_user') and user.tenant_user:
            return user.tenant_user
        if isinstance(user, TenantUser):
            return user
        return None

    def get_queryset(self):
        user = self.request.user
        include_pending = self.request.query_params.get('include_pending') == 'true'

        is_global_admin = bool(
            getattr(user, 'is_superuser', False)
            or getattr(user, 'role', None) in ['super_admin', 'system_admin']
        )
        if is_global_admin:
            tenant_id = self.request.query_params.get('tenant_id')
            qs = TenantUser.objects.filter(tenant_id=tenant_id) if tenant_id else TenantUser.objects.all()
            if self.action == 'list' and not include_pending:
                qs = qs.exclude(created_by_invitation=True, is_active=False)
            elif self.action == 'list' and include_pending:
                qs = qs.filter(created_by_invitation=True, is_active=False)
        else:
            tenant = None
            if hasattr(user, 'tenant') and user.tenant:
                tenant = user.tenant
            elif hasattr(user, 'tenant_user') and user.tenant_user:
                tenant = getattr(user.tenant_user, 'tenant', None)
            elif getattr(user, 'tenant_public_id', None):
                tenant = Tenant.objects.filter(public_id=user.tenant_public_id).first()
            elif getattr(user, 'tenant_id', None):
                tenant = Tenant.objects.filter(public_id=user.tenant_id).first()
                if tenant is None and str(user.tenant_id).isdigit():
                    tenant = Tenant.objects.filter(id=int(user.tenant_id)).first()

            if not tenant:
                return TenantUser.objects.none()

            qs = TenantUser.objects.filter(tenant=tenant)
            if self.action == 'list' and not include_pending:
                qs = qs.exclude(created_by_invitation=True, is_active=False)
            elif self.action == 'list' and include_pending:
                qs = qs.filter(created_by_invitation=True, is_active=False)

            if self.action == 'list' and not self._is_request_root_admin():
                qs = qs.exclude(is_root_admin=True)

        role_filter = self.request.query_params.get('role')
        if role_filter:
            qs = qs.filter(role=role_filter)

        status_filter = self.request.query_params.get('status')
        if status_filter and status_filter != 'all':
            qs = qs.filter(employment_status=status_filter)

        return qs
    
    def get_object(self):
        obj = super().get_object()
        user = self.request.user
        is_global_admin = bool(
            getattr(user, 'is_superuser', False)
            or getattr(user, 'role', None) in ['super_admin', 'system_admin']
        )
        if not is_global_admin:
            tenant = getattr(user, 'tenant_user', None)
            if tenant:
                tenant = tenant.tenant
            if hasattr(user, 'tenant') and user.tenant:
                tenant = user.tenant
            elif getattr(user, 'tenant_public_id', None):
                tenant = Tenant.objects.filter(public_id=user.tenant_public_id).first()
            elif getattr(user, 'tenant_id', None):
                tenant = Tenant.objects.filter(public_id=user.tenant_id).first()
                if tenant is None and str(user.tenant_id).isdigit():
                    tenant = Tenant.objects.filter(id=int(user.tenant_id)).first()
            if tenant and getattr(obj, 'tenant_id', None) != tenant.pk:
                raise permissions.PermissionDenied("You do not have permission to access this user.")

        if getattr(obj, 'is_root_admin', False) and not self._is_request_root_admin():
            raise permissions.PermissionDenied("You do not have permission to access this user.")

        return obj
    
    def get_serializer_context(self):
        context = super().get_serializer_context()
        request = context.get('request')
        user = request.user if request else None

        tenant = None

        # Prefer the explicit tenant relation if the auth object carries it.
        if hasattr(user, 'tenant') and user.tenant:
            tenant = user.tenant
        elif hasattr(user, 'tenant_user') and user.tenant_user:
            tenant = user.tenant_user.tenant
        elif getattr(user, 'tenant_public_id', None):
            try:
                tenant = Tenant.objects.filter(public_id=user.tenant_public_id).first()
            except Exception:
                tenant = None
        elif getattr(user, 'tenant_id', None):
            try:
                tenant = Tenant.objects.filter(public_id=user.tenant_id).first()
                if tenant is None and str(user.tenant_id).isdigit():
                    tenant = Tenant.objects.filter(id=int(user.tenant_id)).first()
            except Exception:
                tenant = None

        if tenant:
            context['tenant'] = tenant

        return context
    
    @action(detail=False, methods=['post'])
    def change_password(self, request):
        """Change current tenant user's password."""
        serializer = PasswordChangeSerializer(
            data=request.data,
            context={'request': request}
        )
        
        if serializer.is_valid():
            user = request.user
            user.set_password(serializer.validated_data['new_password'])
            user.password_changed_at = timezone.now()
            user.save()
            
            from users.models import SecurityEvent
            SecurityEvent.objects.create(
                user=None,
                event_type='password_change',
                severity='INFO',
                description='Password changed successfully',
                ip_address=self.get_client_ip(request),
                user_agent=request.META.get('HTTP_USER_AGENT', '')
            )
            
            return Response({'detail': 'Password changed successfully'})
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['post'], url_path='refresh-password')
    def refresh_password(self, request, pk=None):
        """Generate and save a fresh login password for a staff user."""
        staff = self.get_object()
        generated_password = str(request.data.get('password') or '').strip() or self._generate_temp_password()

        staff.set_password(generated_password)
        staff.password_changed_at = timezone.now()
        staff.save(update_fields=['password', 'password_changed_at'])

        return Response({
            'id': staff.id,
            'employee_id': staff.employee_id or staff.username,
            'email': staff.email,
            'password': generated_password,
            'message': 'Password refreshed successfully.',
        })

    def _generate_temp_password(self):
        import secrets
        import string
        alphabet = string.ascii_letters + string.digits + '!@#$%'
        return ''.join(secrets.choice(alphabet) for _ in range(12))
    
    def get_client_ip(self, request):
        """Get client IP address."""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip

    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            # Only tenant admins or global admins can modify users
            permission_classes = [permissions.IsAuthenticated]
        else:
            permission_classes = [permissions.IsAuthenticated]
        return [permission() for permission in permission_classes]
    
    def _can_edit_user(self, request_user, target_user):
        """Check if request_user can edit target_user."""
        if not request_user:
            return False
        tenant_user = self._get_request_tenant_user()
        if not tenant_user:
            return False
        if tenant_user.role in ['admin', 'hr_manager']:
            return True
        return tenant_user.id == target_user.id
    
    def update(self, request, *args, **kwargs):
        instance = self.get_object()
        if not self._can_edit_user(request.user, instance):
            return Response(
                {'error': 'You can only edit your own profile.'},
                status=status.HTTP_403_FORBIDDEN
            )
        if request.data.get('is_root_admin'):
            if not self._is_request_root_admin():
                raise permissions.PermissionDenied('Only a tenant root admin or global admin can assign root admin privileges.')
            if not instance.is_root_admin:
                raise permissions.PermissionDenied(
                    'Root admin assignment must be done through the dedicated create-root-admin endpoint.'
                )
        return super().update(request, *args, **kwargs)
    
    def partial_update(self, request, *args, **kwargs):
        instance = self.get_object()
        if not self._can_edit_user(request.user, instance):
            return Response(
                {'error': 'You can only edit your own profile.'},
                status=status.HTTP_403_FORBIDDEN
            )
        if request.data.get('is_root_admin'):
            if not self._is_request_root_admin():
                raise permissions.PermissionDenied('Only a tenant root admin or global admin can assign root admin privileges.')
            if not instance.is_root_admin:
                raise permissions.PermissionDenied(
                    'Root admin assignment must be done through the dedicated create-root-admin endpoint.'
                )
        return super().partial_update(request, *args, **kwargs)
    
    @action(detail=False, methods=['get', 'put', 'patch'])
    def me(self, request):
        """Get or update the current authenticated tenant user's own profile."""
        tenant_user = self._get_request_tenant_user()
        if not tenant_user:
            return Response(
                {'error': 'Tenant user profile not found.'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        if request.method == 'GET':
            serializer = self.get_serializer(tenant_user)
            return Response(serializer.data)
        
        partial = request.method == 'PATCH'
        serializer = self.get_serializer(tenant_user, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)
    
    def create(self, request, *args, **kwargs):
        if request.data.get('is_root_admin'):
            raise permissions.PermissionDenied(
                'Root admin users must be created using the dedicated create-root-admin endpoint or during tenant creation.'
            )
        return super().create(request, *args, **kwargs)

    @action(detail=True, methods=['post'])
    def approve(self, request, pk=None):
        """Approve a pending tenant user so they can sign in."""
        user = self.get_object()
        if not self._can_edit_user(request.user, user):
            return Response({'error': 'You can only manage users in your tenant.'}, status=status.HTTP_403_FORBIDDEN)

        if user.is_active:
            return Response({'detail': 'User is already approved.'})

        user.is_active = True
        user.save(update_fields=['is_active'])
        return Response({'detail': 'User approved successfully.'})

    @action(detail=True, methods=['post'])
    def reject(self, request, pk=None):
        """Reject a pending tenant user and keep the account disabled."""
        user = self.get_object()
        if not self._can_edit_user(request.user, user):
            return Response({'error': 'You can only manage users in your tenant.'}, status=status.HTTP_403_FORBIDDEN)

        user.is_active = False
        user.save(update_fields=['is_active'])
        return Response({'detail': 'User rejected successfully.'})

    def perform_create(self, serializer):
        user = self.request.user
        
        # Check permissions
        if hasattr(user, 'tenant_user') and user.tenant_user:
            # Tenant user creating another tenant user
            if user.tenant_user.role not in ['admin', 'hr_manager']:
                raise permissions.PermissionDenied("Only admins and HR managers can create users")
        
        serializer.save()
    
    @action(detail=True, methods=['post'])
    def lock_account(self, request, pk=None):
        """Lock user account."""
        user = self.get_object()
        duration = request.data.get('duration_minutes', 30)
        
        # Check permissions
        request_user = request.user
        if hasattr(request_user, 'tenant_user') and request_user.tenant_user:
            if request_user.tenant_user.role not in ['admin']:
                raise permissions.PermissionDenied("Only admins can lock accounts")
        
        user.lock_account(duration)
        
        return Response({'detail': f'Account locked for {duration} minutes'})
    
    @action(detail=True, methods=['post'])
    def unlock_account(self, request, pk=None):
        """Unlock user account."""
        user = self.get_object()
        
        # Check permissions
        request_user = request.user
        if hasattr(request_user, 'tenant_user') and request_user.tenant_user:
            if request_user.tenant_user.role not in ['admin']:
                raise permissions.PermissionDenied("Only admins can unlock accounts")
        
        user.unlock_account()
        
        return Response({'detail': 'Account unlocked'})

class DepartmentViewSet(viewsets.ModelViewSet):
    """ViewSet for managing departments."""
    serializer_class = DepartmentSerializer
    pagination_class = StandardPagination
    permission_classes = [permissions.IsAuthenticated]
    
    def get_serializer_context(self):
        """Add request to serializer context - this is crucial!"""
        context = super().get_serializer_context()
        context['request'] = self.request
        return context
    
    def get_queryset(self):
        user = self.request.user
        
        if hasattr(user, 'tenant_user') and user.tenant_user:
            try:
                tenant = user.tenant_user.tenant
            except Exception:
                # Tenant relationship missing or invalid; return empty for non-admins
                if not (user.is_superuser or user.role in ['super_admin', 'system_admin']):
                    return Department.objects.none()
                tenant = None
            
            if tenant:
                # Filter by clinical/non-clinical
                is_clinical = self.request.query_params.get('is_clinical')
                if is_clinical is not None:
                    return Department.objects.filter(
                        tenant=tenant,
                        is_clinical=is_clinical.lower() == 'true'
                    )
                
                return Department.objects.filter(tenant=tenant)
        
        # Global admin can see all departments
        if user.is_superuser or user.role in ['super_admin', 'system_admin']:
            tenant_id = self.request.query_params.get('tenant_id')
            if tenant_id:
                return Department.objects.filter(tenant_id=tenant_id)
            return Department.objects.all()
        
        return Department.objects.none()
    
    def perform_create(self, serializer):
        """Create department with proper tenant validation."""
        user = self.request.user
        
        if hasattr(user, 'tenant_user') and user.tenant_user:
            # Only admins and HR managers can create departments
            if user.tenant_user.role not in ['admin', 'hr_manager']:
                raise permissions.PermissionDenied("Only admins and HR managers can create departments")
            
            # The tenant will be resolved in the serializer
            serializer.save()
        else:
            # Global admin creating department
            tenant_id = self.request.data.get('tenant')
            if not tenant_id:
                # If no tenant ID provided, try to resolve from user
                tenant = self._resolve_tenant_from_user(user)
                if tenant:
                    serializer.save(tenant=tenant)
                else:
                    raise serializers.ValidationError({"tenant": ["Tenant ID is required for global admin."]})
            else:
                try:
                    tenant = Tenant.objects.get(public_id=tenant_id)
                    serializer.save(tenant=tenant)
                except Tenant.DoesNotExist:
                    raise serializers.ValidationError({"tenant": ["Invalid tenant ID."]})
    
    def _resolve_tenant_from_user(self, user):
        """Helper method to resolve tenant from user."""
        if hasattr(user, 'tenant_user') and user.tenant_user:
            return user.tenant_user.tenant
        
        # Check if user has tenant directly attached
        if hasattr(user, 'tenant'):
            return user.tenant
        
        return None

        
class TenantSettingViewSet(viewsets.ModelViewSet):
    """ViewSet for managing tenant settings."""
    serializer_class = TenantSettingSerializer
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [JSONParser, MultiPartParser, FormParser]
    
    def get_queryset(self):
        user = self.request.user
        
        if hasattr(user, 'tenant_user') and user.tenant_user:
            # Tenant user can only see their tenant's settings
            return TenantSetting.objects.filter(tenant=user.tenant_user.tenant)
        
        # Global admin can see all settings
        if user.is_superuser or user.role in ['super_admin', 'system_admin']:
            tenant_id = self.request.query_params.get('tenant_id')
            if tenant_id:
                return TenantSetting.objects.filter(tenant_id=tenant_id)
            return TenantSetting.objects.all()
        
        return TenantSetting.objects.none()
    
    def get_permissions(self):
        if self.action in ['create', 'destroy']:
            # Only global admins can create/delete settings
            return [IsSystemAdmin()]
        return [IsTenantRootAdminOrGlobalAdmin()]
    
    @action(detail=False, methods=['get', 'put', 'patch'])
    def current(self, request):
        """Get or update current tenant's settings."""
        user = request.user
        
        if not hasattr(user, 'tenant_user') or not user.tenant_user:
            raise permissions.PermissionDenied("Not a tenant user")
        
        settings = get_object_or_404(TenantSetting, tenant=user.tenant_user.tenant)

        if request.method == 'GET':
            serializer = self.get_serializer(settings)
            return Response(serializer.data)

        partial = request.method in ['PATCH', 'PUT']
        serializer = self.get_serializer(settings, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)


class TenantModuleViewSet(viewsets.ModelViewSet):
    """ViewSet for managing tenant modules."""
    serializer_class = TenantModuleSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        user = self.request.user
        
        if hasattr(user, 'tenant_user') and user.tenant_user:
            # Tenant user can only see their tenant's modules
            return TenantModule.objects.filter(tenant=user.tenant_user.tenant)
        
        # Global admin can see all modules
        if user.is_superuser or user.role in ['super_admin', 'system_admin']:
            tenant_id = self.request.query_params.get('tenant_id')
            if tenant_id:
                return TenantModule.objects.filter(tenant_id=tenant_id)
            return TenantModule.objects.all()
        
        return TenantModule.objects.none()
    
    @action(detail=True, methods=['post'])
    def enable(self, request, pk=None):
        """Enable a module."""
        module = self.get_object()
        
        # Check permissions
        user = request.user
        if hasattr(user, 'tenant_user') and user.tenant_user:
            if user.tenant_user.role not in ['admin']:
                raise permissions.PermissionDenied("Only admins can enable/disable modules")
        
        module.is_enabled = True
        module.enabled_date = timezone.now()
        module.disabled_date = None
        module.save()
        
        return Response({'detail': 'Module enabled'})
    
    @action(detail=True, methods=['post'])
    def disable(self, request, pk=None):
        """Disable a module."""
        module = self.get_object()
        
        # Check permissions
        user = request.user
        if hasattr(user, 'tenant_user') and user.tenant_user:
            if user.tenant_user.role not in ['admin']:
                raise permissions.PermissionDenied("Only admins can enable/disable modules")
        
        module.is_enabled = False
        module.disabled_date = timezone.now()
        module.save()
        
        return Response({'detail': 'Module disabled'})


class TenantInvitationViewSet(viewsets.ModelViewSet):
    """ViewSet for managing tenant invitations."""
    serializer_class = TenantInvitationSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        user = self.request.user
        
        if hasattr(user, 'tenant_user') and user.tenant_user:
            qs = TenantInvitation.objects.filter(tenant=user.tenant_user.tenant)
            include_accepted = self.request.query_params.get('include_accepted') == 'true'
            if not include_accepted:
                qs = qs.exclude(status=TenantInvitation.InvitationStatus.ACCEPTED)
            return qs.order_by('archived', '-created_at')
        
        return TenantInvitation.objects.none()
    
    def get_serializer_context(self):
        context = super().get_serializer_context()
        
        # Add tenant to context
        user = self.request.user
        if hasattr(user, 'tenant_user') and user.tenant_user:
            context['tenant'] = user.tenant_user.tenant

        request_data = self.request.data if hasattr(self.request, 'data') else {}
        frontend_base_url = None
        if hasattr(request_data, 'get'):
            frontend_base_url = request_data.get('frontend_base_url')

        if not frontend_base_url:
            frontend_base_url = (
                self.request.headers.get('X-Frontend-Base-Url') or
                self.request.headers.get('X-Frontend-URL') or
                self.request.headers.get('Origin')
            )

        if frontend_base_url:
            context['frontend_base_url'] = frontend_base_url
        
        return context
    
    def _ensure_admin_or_hr(self, user, invitation):
        if not hasattr(user, 'tenant_user') or not user.tenant_user:
            raise permissions.PermissionDenied("Only tenant admins and HR managers can manage invitations")
        if user.tenant_user.role not in ['admin', 'hr_manager']:
            raise permissions.PermissionDenied("Only admins and HR managers can manage invitations")
        if invitation.tenant != user.tenant_user.tenant:
            raise permissions.PermissionDenied("You can only manage invitations for your own tenant")
    
    def perform_create(self, serializer):
        user = self.request.user
        
        if hasattr(user, 'tenant_user') and user.tenant_user:
            if user.tenant_user.role not in ['admin', 'hr_manager']:
                raise permissions.PermissionDenied("Only admins and HR managers can send invitations")
            
            serializer.save(
                invited_by=user.tenant_user,
                tenant=user.tenant_user.tenant
            )
    
    def destroy(self, request, *args, **kwargs):
        invitation = self.get_object()
        self._ensure_admin_or_hr(request.user, invitation)
        return super().destroy(request, *args, **kwargs)
    
    @action(detail=True, methods=['post'])
    def resend(self, request, pk=None):
        """Resend an invitation."""
        invitation = self.get_object()
        self._ensure_admin_or_hr(request.user, invitation)
        
        if invitation.status != TenantInvitation.InvitationStatus.PENDING:
            return Response(
                {'error': 'Cannot resend non-pending invitation'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        invitation.expires_at = timezone.now() + timezone.timedelta(days=7)
        invitation.save()
        
        return Response({'detail': 'Invitation resent'})
    
    @action(detail=True, methods=['post'])
    def revoke(self, request, pk=None):
        """Revoke an invitation."""
        invitation = self.get_object()
        self._ensure_admin_or_hr(request.user, invitation)
        invitation.status = TenantInvitation.InvitationStatus.REVOKED
        invitation.save()
        
        return Response({'detail': 'Invitation revoked'})
    
    @action(detail=True, methods=['post'])
    def archive(self, request, pk=None):
        """Archive an invitation."""
        invitation = self.get_object()
        self._ensure_admin_or_hr(request.user, invitation)
        invitation.archived = True
        invitation.save()
        
        return Response({'detail': 'Invitation archived'})
    
    @action(detail=True, methods=['post'])
    def unarchive(self, request, pk=None):
        """Unarchive an invitation."""
        invitation = self.get_object()
        self._ensure_admin_or_hr(request.user, invitation)
        invitation.archived = False
        invitation.save()
        
        return Response({'detail': 'Invitation unarchived'})



class AcceptInvitationView(APIView):
    """Accept a tenant invitation."""
    permission_classes = [permissions.AllowAny]
    
    def post(self, request):
        serializer = AcceptInvitationSerializer(data=request.data)
        
        if serializer.is_valid():
            user = serializer.save()
            
            # Return user data
            user_serializer = TenantUserSerializer(user)
            return Response({
                'detail': 'Invitation accepted successfully',
                'user': user_serializer.data
            })
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)




class TenantActivityLogViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet for viewing tenant activity logs."""
    serializer_class = TenantActivityLogSerializer
    pagination_class = StandardPagination
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        user = self.request.user
        
        if hasattr(user, 'tenant_user') and user.tenant_user:
            # Tenant user can see their tenant's activity logs
            return TenantActivityLog.objects.filter(tenant=user.tenant_user.tenant)
        
        # Global admin can see all activity logs
        if user.is_superuser or user.role in ['super_admin', 'system_admin']:
            tenant_id = self.request.query_params.get('tenant_id')
            if tenant_id:
                return TenantActivityLog.objects.filter(tenant_id=tenant_id)
            return TenantActivityLog.objects.all()
        
        return TenantActivityLog.objects.none()
    
    @action(detail=False, methods=['get'])
    def summary(self, request):
        """Get activity log summary."""
        user = request.user
        
        if not hasattr(user, 'tenant_user') or not user.tenant_user:
            raise permissions.PermissionDenied("Not a tenant user")
        
        tenant = user.tenant_user.tenant
        
        # Get activity counts by user
        activity_by_user = TenantActivityLog.objects.filter(
            tenant=tenant
        ).values(
            'user__username', 'user__first_name', 'user__last_name'
        ).annotate(
            count=Count('id')
        ).order_by('-count')[:10]
        
        # Get activity counts by action
        activity_by_action = TenantActivityLog.objects.filter(
            tenant=tenant
        ).values('action').annotate(
            count=Count('id')
        ).order_by('-count')[:10]
        
        # Get recent activities
        recent_activities = TenantActivityLog.objects.filter(
            tenant=tenant
        ).select_related('user').order_by('-created_at')[:20]
        
        recent_serializer = self.get_serializer(recent_activities, many=True)
        
        return Response({
            'activity_by_user': list(activity_by_user),
            'activity_by_action': list(activity_by_action),
            'recent_activities': recent_serializer.data,
        })


class TenantBackupViewSet(viewsets.ModelViewSet):
    """ViewSet for managing tenant backups."""
    serializer_class = TenantBackupSerializer
    pagination_class = StandardPagination
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        user = self.request.user
        
        if hasattr(user, 'tenant_user') and user.tenant_user:
            # Tenant admin can see their tenant's backups
            if user.tenant_user.role == 'admin':
                return TenantBackup.objects.filter(tenant=user.tenant_user.tenant)
        
        # Global admin can see all backups
        if user.is_superuser or user.role in ['super_admin', 'system_admin']:
            tenant_id = self.request.query_params.get('tenant_id')
            if tenant_id:
                return TenantBackup.objects.filter(tenant_id=tenant_id)
            return TenantBackup.objects.all()
        
        return TenantBackup.objects.none()
    
    def get_permissions(self):
        if self.action in ['create', 'destroy']:
            # Only global admins can create/delete backups
            return [IsSystemAdmin()]
        return super().get_permissions()
    
    @action(detail=True, methods=['post'])
    def restore(self, request, pk=None):
        """Restore from a backup."""
        backup = self.get_object()
        
        # TODO: Implement restore logic
        # This would involve:
        # 1. Validating backup integrity
        # 2. Taking a pre-restore backup
        # 3. Restoring database and files
# 4. Verifying restore
        
        return Response({
            'detail': 'Restore initiated',
            'backup_id': backup.id,
            'status': 'queued'
        })


class BulkTenantUserUploadViewSet(viewsets.ModelViewSet):
    """ViewSet for tracking bulk tenant user (staff) uploads."""
    queryset = BulkTenantUserUpload.objects.all()
    serializer_class = BulkTenantUserUploadSerializer
    permission_classes = [permissions.IsAuthenticated]

    def _get_request_tenant(self):
        user = getattr(self.request, 'user', None)
        if user is None:
            return None
        if hasattr(user, 'tenant_user') and getattr(user, 'tenant_user', None):
            return user.tenant_user.tenant
        if hasattr(user, 'tenant') and getattr(user, 'tenant', None):
            return user.tenant
        return None

    def get_queryset(self):
        tenant = self._get_request_tenant()
        if tenant:
            return BulkTenantUserUpload.objects.filter(tenant=tenant)
        return BulkTenantUserUpload.objects.none()

    def get_serializer_context(self):
        context = super().get_serializer_context()
        tenant = self._get_request_tenant()
        if tenant:
            context['tenant'] = tenant
        return context

    @action(detail=False, methods=['post'], serializer_class=BulkTenantUserUploadSerializer)
    def upload(self, request):
        """Accept a CSV file and start background processing of tenant users."""
        file_obj = request.FILES.get('file')
        if not file_obj:
            return Response({'error': 'No file provided.'}, status=status.HTTP_400_BAD_REQUEST)

        tenant = self._get_request_tenant()
        if not tenant:
            return Response({'error': 'No tenant associated with your account.'}, status=status.HTTP_400_BAD_REQUEST)

        uploaded_by = None
        user = getattr(request, 'user', None)
        if user is not None and hasattr(user, 'tenant_user') and getattr(user, 'tenant_user', None):
            uploaded_by = user.tenant_user
        elif isinstance(user, TenantUser):
            uploaded_by = user

        upload = BulkTenantUserUpload.objects.create(
            tenant=tenant,
            uploaded_by=uploaded_by,
            file=file_obj,
            original_filename=file_obj.name,
            status='processing',
            started_at=timezone.now(),
        )

        thread = threading.Thread(target=_process_bulk_user_upload, args=(upload.id,))
        thread.start()

        serializer = self.get_serializer(upload)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


def _normalize_role(value):
    """Map a role string from a CSV to a valid TenantUser.UserRole value."""
    if not value:
        return 'staff'
    normalized = str(value).strip().lower()
    mapping = {
        'admin': 'admin',
        'administrator': 'admin',
        'doctor': 'doctor',
        'physician': 'doctor',
        'consultant': 'doctor',
        'nurse': 'nurse',
        'registered nurse': 'nurse',
        'pharmacist': 'pharmacist',
        'lab_tech': 'lab_tech',
        'lab technician': 'lab_tech',
        'lab_manager': 'lab_manager',
        'lab manager': 'lab_manager',
        'receptionist': 'receptionist',
        'reception': 'receptionist',
        'accountant': 'accountant',
        'hr_manager': 'hr_manager',
        'hr manager': 'hr_manager',
        'inventory_manager': 'inventory_manager',
        'inventory manager': 'inventory_manager',
        'patient': 'patient',
    }
    return mapping.get(normalized, normalized if normalized in TenantUser.UserRole.values else 'staff')


def _parse_employment_date(value):
    """Parse a date string; return None for empty input."""
    if not value or not str(value).strip():
        return None
    dof = str(value).strip()
    for fmt in ('%Y-%m-%d', '%d/%m/%Y', '%m/%d/%Y'):
        try:
            from datetime import datetime
            return datetime.strptime(dof, fmt).date()
        except Exception:
            pass
    raise ValueError(f'Invalid date format: {dof}')


def _process_bulk_user_upload(upload_id):
    """Background processor for bulk tenant user uploads."""
    from django.db import close_old_connections
    close_old_connections()
    try:
        upload = BulkTenantUserUpload.objects.get(id=upload_id)
        upload.status = 'processing'
        upload.started_at = timezone.now()
        upload.save(update_fields=['status', 'started_at'])

        tenant = upload.tenant
        file_path = upload.file.path
        errors = []
        success_count = 0
        failure_count = 0
        total_records = 0

        try:
            # Switch to the tenant schema for all TenantUser writes.
            connection.set_tenant(tenant)

            with open(file_path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                rows = list(reader)
                total_records = len(rows)
                upload.total_records = total_records
                upload.save(update_fields=['total_records'])

                for idx, row in enumerate(rows):
                    try:
                        first_name = (row.get('first_name') or row.get('First Name') or '').strip()
                        last_name = (row.get('last_name') or row.get('Last Name') or '').strip()
                        email = (row.get('email') or row.get('Email') or '').strip().lower()
                        phone = (row.get('phone') or row.get('Phone') or '').strip()
                        role = (row.get('role') or row.get('Role') or '').strip()
                        department_name = (row.get('department') or row.get('Department') or '').strip()
                        designation = (row.get('designation') or row.get('Designation') or '').strip()
                        employee_id = (row.get('employee_id') or row.get('Employee ID') or '').strip()
                        employment_date = (row.get('employment_date') or row.get('Employment Date') or '').strip()
                        password = (row.get('password') or row.get('Password') or '').strip() or 'TempPass123!'

                        if not first_name or not last_name:
                            raise ValueError('First name and last name are required.')
                        if not email:
                            raise ValueError('Email is required.')
                        if not role:
                            raise ValueError('Role is required.')

                        try:
                            validate_email(email)
                        except Exception:
                            raise ValueError(f'Invalid email format: {email}')

                        normalized_role = _normalize_role(role)

                        if TenantUser.objects.filter(tenant=tenant, email=email).exists():
                            raise ValueError(f'A user with email "{email}" already exists in this tenant.')

                        if employee_id:
                            conflicting = _check_employee_id_globally_unique(employee_id, exclude_tenant=tenant)
                            if conflicting:
                                raise ValueError(
                                    f'Employee ID "{employee_id}" is already used in tenant '
                                    f'"{conflicting.name}" ({conflicting.domain}).'
                                )

                        department = None
                        if department_name:
                            department = Department.objects.filter(
                                tenant=tenant,
                                name__iexact=department_name,
                            ).first() or Department.objects.filter(
                                tenant=tenant,
                                code__iexact=department_name,
                            ).first()

                        validated_data = {
                            'tenant': tenant,
                            'first_name': first_name,
                            'last_name': last_name,
                            'email': email,
                            'phone': phone or '',
                            'role': normalized_role,
                            'designation': designation,
                            'employee_id': employee_id or None,
                            'employment_date': _parse_employment_date(employment_date),
                            'employment_status': 'active',
                            'is_staff': True,
                            'is_active': True,
                        }
                        if department:
                            validated_data['department'] = department

                        with transaction.atomic():
                            user = TenantUser.objects.create(**validated_data)
                            user.set_password(password)
                            user.save()

                        success_count += 1
                    except Exception as row_err:
                        failure_count += 1
                        errors.append({
                            'row': idx + 2,
                            'data': dict(row),
                            'error': f"{type(row_err).__name__}: {str(row_err)}"
                        })

                    upload.processed_records = idx + 1
                    upload.success_count = success_count
                    upload.failure_count = failure_count
                    upload.errors = errors
                    try:
                        upload.save(update_fields=['processed_records', 'success_count', 'failure_count', 'errors'])
                    except Exception:
                        pass

            upload.status = 'completed'
            upload.completed_at = timezone.now()
            upload.result_message = f"Processed {total_records} records. {success_count} succeeded, {failure_count} failed."
            upload.save(update_fields=['status', 'completed_at', 'result_message'])

        except Exception as e:
            upload.status = 'failed'
            upload.completed_at = timezone.now()
            upload.result_message = str(e)
            upload.save(update_fields=['status', 'completed_at', 'result_message'])
        finally:
            connection.set_schema_to_public()

    except BulkTenantUserUpload.DoesNotExist:
        pass


class CommunicationProfileViewSet(viewsets.ModelViewSet):
    """ViewSet for managing per-tenant communication profiles."""
    serializer_class = CommunicationProfileSerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = StandardPagination

    def get_queryset(self):
        user = self.request.user
        is_global_admin = bool(
            getattr(user, 'is_superuser', False)
            or getattr(user, 'role', None) in ['super_admin', 'system_admin']
        )
        if is_global_admin:
            return CommunicationProfile.objects.all()

        tenant = None
        if hasattr(user, 'tenant') and user.tenant:
            tenant = user.tenant
        elif hasattr(user, 'tenant_user') and user.tenant_user:
            tenant = user.tenant_user.tenant
        elif getattr(user, 'tenant_public_id', None):
            tenant = Tenant.objects.filter(public_id=user.tenant_public_id).first()
        elif getattr(user, 'tenant_id', None):
            tenant = Tenant.objects.filter(public_id=user.tenant_id).first()
            if tenant is None and str(user.tenant_id).isdigit():
                tenant = Tenant.objects.filter(id=int(user.tenant_id)).first()

        if tenant:
            return CommunicationProfile.objects.filter(tenant=tenant)
        return CommunicationProfile.objects.none()

    def perform_create(self, serializer):
        tenant = self._resolve_tenant()
        if not tenant:
            raise serializers.ValidationError({'tenant': 'Tenant is required.'})
        serializer.save(tenant=tenant)

    def perform_update(self, serializer):
        serializer.save()

    @action(detail=False, methods=['get'], url_path='current')
    def current(self, request):
        """Return the communication profile for the current user's tenant."""
        tenant = self._resolve_tenant()
        if not tenant:
            return Response({'detail': 'Tenant not resolved.'}, status=status.HTTP_400_BAD_REQUEST)
        profile = getattr(tenant, 'communication_profile', None)
        if not profile:
            profile = CommunicationProfile.objects.create(tenant=tenant)
        serializer = self.get_serializer(profile)
        return Response(serializer.data)

    def _resolve_tenant(self):
        user = self.request.user
        if hasattr(user, 'tenant') and user.tenant:
            return user.tenant
        if hasattr(user, 'tenant_user') and user.tenant_user:
            return user.tenant_user.tenant
        if getattr(user, 'tenant_public_id', None):
            return Tenant.objects.filter(public_id=user.tenant_public_id).first()
        if getattr(user, 'tenant_id', None):
            tenant = Tenant.objects.filter(public_id=user.tenant_id).first()
            if tenant is None and str(user.tenant_id).isdigit():
                tenant = Tenant.objects.filter(id=int(user.tenant_id)).first()
            return tenant
        return None


class ExternalServiceProfileViewSet(viewsets.ModelViewSet):
    """Tenant root-admin configuration for LIS, PACS, FHIR, and Mirth."""
    serializer_class = ExternalServiceProfileSerializer
    permission_classes = [IsTenantRootAdminOrGlobalAdmin]

    def get_queryset(self):
        tenant = self._resolve_tenant()
        return ExternalServiceProfile.objects.filter(tenant=tenant) if tenant else ExternalServiceProfile.objects.none()

    def _resolve_tenant(self):
        user = self.request.user
        tenant_user = getattr(user, 'tenant_user', None)
        if tenant_user:
            return tenant_user.tenant
        if getattr(user, 'tenant', None):
            return user.tenant
        tenant_id = self.request.query_params.get('tenant_id')
        return Tenant.objects.filter(public_id=tenant_id).first() if tenant_id else None

    @action(detail=False, methods=['get', 'put', 'patch'], url_path='current')
    def current(self, request):
        tenant = self._resolve_tenant()
        if not tenant:
            return Response({'detail': 'Tenant not resolved.'}, status=status.HTTP_400_BAD_REQUEST)
        profile, _ = ExternalServiceProfile.objects.get_or_create(tenant=tenant)
        if request.method == 'GET':
            return Response(self.get_serializer(profile).data)
        serializer = self.get_serializer(profile, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)


class TenantSupportTicketViewSet(viewsets.ModelViewSet):
    """Tenant-facing support tickets."""
    serializer_class = SupportTicketSerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = StandardPagination

    def get_queryset(self):
        user = self.request.user
        tenant = None
        if hasattr(user, 'tenant_user') and user.tenant_user:
            tenant = user.tenant_user.tenant
        elif hasattr(user, 'tenant') and user.tenant:
            tenant = user.tenant

        if not tenant:
            return SupportTicket.objects.none()

        queryset = SupportTicket.objects.filter(tenant=tenant).order_by('-created_at')
        status_filter = self.request.query_params.get('status')
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        return queryset

    def perform_create(self, serializer):
        user = self.request.user
        tenant = None
        if hasattr(user, 'tenant_user') and user.tenant_user:
            tenant = user.tenant_user.tenant
        elif hasattr(user, 'tenant') and user.tenant:
            tenant = user.tenant

        if not tenant:
            raise serializers.ValidationError({'tenant': 'Tenant is required.'})

        creator_name = ''
        creator_email = ''
        creator_role = 'tenant_admin'
        if hasattr(user, 'tenant_user') and user.tenant_user:
            creator_name = user.tenant_user.get_full_name() or user.tenant_user.username
            creator_email = user.tenant_user.email or ''
            creator_role = user.tenant_user.role or 'tenant_admin'
        elif hasattr(user, 'email'):
            creator_name = user.get_full_name() or user.username
            creator_email = user.email or ''
            creator_role = getattr(user, 'role', 'tenant_admin')

        serializer.save(
            tenant=tenant,
            created_by_name=creator_name,
            created_by_email=creator_email,
            created_by_role=creator_role,
        )


# ---------------------------------------------------------------------------
# Helpers & shared configuration for self-service signup / payments
# ---------------------------------------------------------------------------
def _ensure_public_schema():
    """Ensure DB queries run on the public schema (global data)."""
    try:
        connection.set_schema_to_public()
    except Exception:
        pass


def _get_system_setting(key, default=None):
    """Read a platform SystemSetting value (fail-open to ``default``)."""
    try:
        return SystemSetting.objects.get(key=key).value
    except SystemSetting.DoesNotExist:
        return default


def _bool_setting(value, default=False):
    if value is None:
        return default
    return str(value).strip().lower() not in ('false', '0', 'no', 'off', '')


DEFAULT_SIGNUP_DEPARTMENTS = [
    {'name': 'Administration', 'code': 'ADMIN', 'is_clinical': False},
    {'name': 'Outpatient Department', 'code': 'OPD', 'is_clinical': True},
    {'name': 'Inpatient Department', 'code': 'IPD', 'is_clinical': True},
    {'name': 'Emergency Department', 'code': 'ER', 'is_clinical': True},
    {'name': 'Pharmacy', 'code': 'PHARM', 'is_clinical': False},
    {'name': 'Laboratory', 'code': 'LAB', 'is_clinical': False},
    {'name': 'Radiology', 'code': 'RAD', 'is_clinical': False},
    {'name': 'Billing', 'code': 'BILL', 'is_clinical': False},
]


def _generate_unique_tenant_code(name):
    """Generate a unique tenant code mirroring Tenant.generate_tenant_code()."""
    import random
    import string
    base = (name[:3].upper() if name else 'TNT') or 'TNT'
    for _ in range(12):
        code = f"{base}{''.join(random.choices(string.digits, k=4))}"
        if not Tenant.objects.filter(code=code).exists():
            return code
    return f"{base}{uuid.uuid4().hex[:8].upper()}"


def _generate_unique_domain(code):
    """Generate a unique tenant subdomain on the platform domain."""
    candidate = f"{code.lower()}.smartcarehms.local"
    counter = 1
    while Tenant.objects.filter(domain=candidate).exists():
        counter += 1
        candidate = f"{code.lower()}-{counter}.smartcarehms.local"
    return candidate


def _create_root_admin(tenant, admin_data, is_active=False):
    """Create the tenant root admin (mirrors superadmin TenantAdminCreateView)."""
    first_name = admin_data['admin_first_name']
    last_name = admin_data['admin_last_name']
    email = admin_data['admin_email']
    phone = admin_data.get('admin_phone') or ''

    username_base = f"{first_name.lower()}.{last_name.lower()}".replace(' ', '_')
    unique_username = username_base
    counter = 1
    while TenantUser.objects.filter(tenant=tenant, username=unique_username).exists():
        unique_username = f"{username_base}{counter}"
        counter += 1

    admin_user = TenantUser.objects.create(
        tenant=tenant,
        username=unique_username,
        email=email,
        first_name=first_name,
        last_name=last_name,
        phone=phone,
        role='admin',
        employee_id=None,
        is_staff=True,
        is_active=is_active,
        is_root_admin=True,
    )
    if admin_data.get('password_hash'):
        admin_user.password = admin_data['password_hash']
    else:
        admin_user.set_password(admin_data['password'])
    admin_user.save()
    return admin_user


def _generate_verification_token(tenant, admin_user):
    payload = {
        'tenant_public_id': str(tenant.public_id),
        'admin_email': admin_user.email,
        'admin_id': admin_user.id,
    }
    return signed_dumps(payload, salt='tenant-email-verification')


def _send_verification_email(tenant, admin_user):
    """Send the email-verification message using tenant-specific email configuration.

    Returns ``(sent: bool, error: str|None)``. Uses the tenant's configured sender
    email when available, falling back to global defaults.
    """
    from tenants.communication import build_email_context, send_tenant_email
    
    token = _generate_verification_token(tenant, admin_user)
    verify_url = f"{getattr(settings, 'FRONTEND_URL', 'http://localhost:5173')}/verify-email?token={token}"

    base_context = {
        'admin_name': admin_user.get_full_name() or admin_user.username,
        'tenant_name': tenant.name,
        'verify_url': verify_url,
        'login_id': admin_user.employee_id or admin_user.id,
        'admin_email': admin_user.email,
        'year': datetime.date.today().year,
        'app_name': getattr(settings, 'APP_NAME', 'SmartCare HMS'),
        'support_email': _get_system_setting('support_email', 'support@smartcarehms.com'),
    }
    context = build_email_context(tenant, extra=base_context)
    subject = f'Verify your {tenant.name} account'
    try:
        html_message = render_to_string('tenants/email_verification_email.html', context)
        plain_message = render_to_string('tenants/email_verification_email.txt', context)
        send_tenant_email(
            tenant=tenant,
            subject=subject,
            message=plain_message,
            recipient_list=[admin_user.email],
            html_message=html_message,
            fail_silently=False,
        )
        return True, None
    except Exception as exc:
        logger.error('Failed to send verification email to %s: %s', admin_user.email, exc)
        return False, str(exc)


def _paypal_access_token():
    client_id = get_payment_setting('paypal_client_id')
    client_secret = get_payment_setting('paypal_client_secret')
    response = requests.post(
        f"{get_payment_setting('paypal_base_url', 'https://api-m.sandbox.paypal.com')}/v1/oauth2/token",
        auth=(client_id, client_secret),
        data={'grant_type': 'client_credentials'},
        headers={'Accept': 'application/json', 'Accept-Language': 'en_US'},
        timeout=15,
    )
    response.raise_for_status()
    return response.json()['access_token']


def _initialize_signup_payment(plan, billing_period, payment_method, signup_data):
    amounts = {
        'monthly': plan.price_monthly,
        'quarterly': plan.price_quarterly,
        'yearly': plan.price_yearly,
    }
    amount = amounts[billing_period]
    if amount <= 0:
        raise ValueError('The selected subscription plan must have a payable price.')
    if payment_method == 'paystack' and not payment_setting_configured('paystack_secret_key'):
        raise ValueError('Paystack is not configured.')
    if payment_method == 'paypal' and not (
        payment_setting_configured('paypal_client_id') and payment_setting_configured('paypal_client_secret')
    ):
        raise ValueError('PayPal is not configured.')
    if payment_method == 'paypal' and plan.currency not in {'USD', 'EUR', 'GBP', 'CAD', 'AUD'}:
        raise ValueError('PayPal requires a plan currency supported by PayPal, such as USD, EUR, GBP, CAD, or AUD.')

    reference = f"HMS-SIGNUP-{uuid.uuid4().hex[:24].upper()}"
    payment = SubscriptionPayment.objects.create(
        tenant=None,
        plan=plan,
        reference=reference,
        amount=amount,
        currency=plan.currency,
        billing_period=billing_period,
        gateway=payment_method,
        signup_data=signup_data,
    )
    try:
        if payment_method == 'paystack':
            response = requests.post(
                'https://api.paystack.co/transaction/initialize',
                headers={'Authorization': f"Bearer {get_payment_setting('paystack_secret_key')}"},
                json={
                    'email': signup_data['email'],
                    'amount': int(amount * 100),
                    'currency': plan.currency,
                    'reference': reference,
                    'callback_url': f'{settings.FRONTEND_URL}/signup?payment=complete',
                    'metadata': {'payment_id': payment.id, 'signup': True},
                },
                timeout=15,
            )
            gateway_data = response.json()
            if not response.ok or not gateway_data.get('status'):
                raise requests.RequestException(gateway_data.get('message', 'Payment initialization failed'))
            checkout = {
                'authorization_url': gateway_data['data']['authorization_url'],
                'access_code': gateway_data['data']['access_code'],
            }
        else:
            token = _paypal_access_token()
            response = requests.post(
                f"{get_payment_setting('paypal_base_url', 'https://api-m.sandbox.paypal.com')}/v2/checkout/orders",
                headers={'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'},
                json={
                    'intent': 'CAPTURE',
                    'purchase_units': [{
                        'reference_id': reference,
                        'custom_id': reference,
                        'amount': {'currency_code': plan.currency, 'value': f'{amount:.2f}'},
                    }],
                    'application_context': {
                        'return_url': f'{settings.FRONTEND_URL}/signup?payment=complete',
                        'cancel_url': f'{settings.FRONTEND_URL}/signup?payment=cancelled',
                    },
                },
                timeout=15,
            )
            response.raise_for_status()
            gateway_data = response.json()
            approval = next((link['href'] for link in gateway_data.get('links', []) if link.get('rel') == 'approve'), None)
            if not approval:
                raise requests.RequestException('PayPal did not return an approval URL.')
            checkout = {'authorization_url': approval, 'order_id': gateway_data['id']}
    except (requests.RequestException, ValueError) as exc:
        payment.status = SubscriptionPayment.Status.FAILED
        payment.gateway_response = {'error': str(exc)}
        payment.save(update_fields=['status', 'gateway_response', 'updated_at'])
        raise RuntimeError('Unable to initialize payment.') from exc

    payment.gateway_response = gateway_data.get('data', {})
    payment.save(update_fields=['gateway_response', 'updated_at'])
    return {
        'reference': reference,
        'gateway': payment_method,
        **checkout,
        'amount': str(amount),
        'currency': plan.currency,
        'billing_period': billing_period,
    }


def _provision_paid_signup(payment):
    data = payment.signup_data
    country = Country.objects.get(id=data['country_id'])
    facility_type = FacilityType.objects.get(id=data['facility_type_id'])
    registration_number = data['registration_number']
    code = _generate_unique_tenant_code(data['hospital_name'])
    domain = _generate_unique_domain(code)
    tenant = Tenant.objects.create(
        name=data['hospital_name'], code=code, domain=domain,
        schema_name=f'tenant_{code.lower()}', email=data['email'], phone=data['phone'],
        address=data['address'], city=data['city'], state_id=data.get('state_id'),
        lga_id=data.get('lga_id'), country=country, facility_type=facility_type,
        registration_number=registration_number, tax_id=data.get('tax_id', ''),
        website=data.get('website', ''), subscription_plan=payment.plan,
        subscription_status=Tenant.SubscriptionStatus.SUSPENDED,
        monthly_fee=0, billing_email=data['email'], payment_method=payment.gateway,
        is_active=True,
    )
    TenantSetting.objects.create(tenant=tenant)
    CommunicationProfile.objects.create(tenant=tenant)
    for dept in DEFAULT_SIGNUP_DEPARTMENTS:
        Department.objects.create(tenant=tenant, **dept)
    admin_user = _create_root_admin(
        tenant,
        {
            'admin_first_name': data['admin_first_name'],
            'admin_last_name': data['admin_last_name'],
            'admin_email': data['admin_email'],
            'admin_phone': data.get('admin_phone', ''),
            'password_hash': data['password_hash'],
        },
        is_active=False,
    )
    TenantDomain.objects.get_or_create(domain=domain, defaults={'tenant': tenant, 'is_primary': True})
    try:
        tenant.create_schema()
    except Exception as exc:
        logger.warning('create_schema failed for tenant %s: %s', tenant.id, exc)
    return tenant, admin_user


class SelfSignupView(APIView):
    """Public, unauthenticated tenant signup.

    Creates a trial tenant + root admin (inactive until email verification),
    mirroring ``superadmin.TenantAdminCreateView`` provisioning so admin-created
    and self-service tenants are provisioned identically.
    """
    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    def post(self, request):
        _ensure_public_schema()
        serializer = SelfSignupSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        if not _bool_setting(_get_system_setting('allow_new_signups', 'true')):
            return Response({'error': 'Self-service signups are currently closed.'},
                            status=status.HTTP_423_LOCKED)

        configured_payment_method = _get_system_setting('subscription_payment_method', 'paystack')
        if data.get('payment_method', 'paystack') != configured_payment_method:
            return Response({'error': 'The selected payment method is not currently available.'},
                            status=status.HTTP_400_BAD_REQUEST)

        plan = None
        plan_id = data.get('plan_id')
        if plan_id:
            try:
                plan = SubscriptionPlan.objects.get(id=plan_id, is_active=True)
            except SubscriptionPlan.DoesNotExist:
                return Response({'error': 'Invalid subscription plan.'},
                                status=status.HTTP_400_BAD_REQUEST)
        if plan is None:
            plan = (
                SubscriptionPlan.objects.filter(is_default=True, is_active=True).first()
                or SubscriptionPlan.objects.filter(is_active=True)
                .order_by('display_order', 'price_monthly').first()
            )
        if plan is None:
            return Response({'error': 'No active subscription plan is available.'},
                            status=status.HTTP_503_SERVICE_UNAVAILABLE)

        if Tenant.objects.filter(email=data['email']).exists():
            return Response({'error': {'email': 'This billing email is already registered.'}},
                            status=status.HTTP_400_BAD_REQUEST)

        country = None
        country_id = data.get('country')
        try:
            country = Country.objects.get(id=country_id) if country_id else Country.objects.first()
        except Country.DoesNotExist:
            return Response({'error': {'country': 'Invalid country.'}}, status=status.HTTP_400_BAD_REQUEST)
        if country is None:
            return Response({'error': 'No country is available on the platform.'},
                            status=status.HTTP_503_SERVICE_UNAVAILABLE)

        facility_type = None
        if data.get('facility_type'):
            try:
                facility_type = FacilityType.objects.get(id=data['facility_type'])
            except FacilityType.DoesNotExist:
                return Response({'error': {'facility_type': 'Invalid facility type.'}},
                                status=status.HTTP_400_BAD_REQUEST)
        if facility_type is None:
            facility_type = FacilityType.objects.first()
        if facility_type is None:
            return Response({'error': 'No facility type is available on the platform.'},
                            status=status.HTTP_503_SERVICE_UNAVAILABLE)

        registration_number = (data.get('registration_number') or '').strip().upper()
        if not registration_number:
            registration_number = f"REG-{uuid.uuid4().hex[:8].upper()}"
        signup_data = {
            'hospital_name': data['hospital_name'],
            'email': data['email'], 'phone': data['phone'],
            'address': data['address'], 'city': data['city'],
            'state_id': data.get('state'), 'lga_id': data.get('lga'),
            'country_id': country.id, 'facility_type_id': facility_type.id,
            'registration_number': registration_number,
            'tax_id': (data.get('tax_id') or '').strip(),
            'website': (data.get('website') or '').strip(),
            'admin_first_name': data['admin_first_name'],
            'admin_last_name': data['admin_last_name'],
            'admin_email': data['admin_email'],
            'admin_phone': data.get('admin_phone') or '',
            'password_hash': make_password(data['password']),
        }
        try:
            checkout = _initialize_signup_payment(
                plan, data.get('billing_period', 'monthly'), data.get('payment_method', 'paystack'), signup_data
            )
        except (ValueError, RuntimeError) as exc:
            return Response({'error': str(exc)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        return Response({
            'payment_pending': True,
            'payment_required': True,
            'checkout': checkout,
            'message': 'Complete payment to finish creating your workspace and root administrator account.',
        }, status=status.HTTP_202_ACCEPTED)


class VerifyEmailView(APIView):
    """Public, unauthenticated email verification endpoint."""
    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    def post(self, request):
        token = request.data.get('token') or request.GET.get('token')
        if not token:
            return Response({'error': 'Verification token is required.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            payload = signed_loads(token, max_age=86400, salt='tenant-email-verification')
        except SignatureExpired:
            return Response({'error': 'Verification link has expired. Please sign up again.'},
                            status=status.HTTP_410_GONE)
        except BadSignature:
            return Response({'error': 'Invalid verification link.'}, status=status.HTTP_400_BAD_REQUEST)

        _ensure_public_schema()
        tenant = get_object_or_404(Tenant, public_id=payload.get('tenant_public_id'))
        admin_user = TenantUser.objects.filter(
            tenant=tenant, email__iexact=payload.get('admin_email'), is_root_admin=True
        ).first()
        if not admin_user:
            return Response({'error': 'Root admin user not found.'}, status=status.HTTP_404_NOT_FOUND)

        was_inactive = not admin_user.is_active
        admin_user.is_active = True
        admin_user.is_staff = True
        admin_user.account_locked_until = None
        admin_user.failed_login_attempts = 0
        admin_user.save(update_fields=['is_active', 'is_staff', 'account_locked_until',
                                       'failed_login_attempts'])

        AuditLog.objects.create(
            tenant=tenant,
            action='verify_email',
            resource_type='tenant_user',
            resource_id=str(admin_user.id),
            actor=payload.get('admin_email', ''),
            title='Email verified; root admin activated',
            new_values={'tenant': str(tenant.public_id), 'is_active': True},
        )
        return Response({
            'verified': True,
            'message': 'Account verified successfully. You can now log in.',
            'login_url': '/login',
            'payment_required': tenant.subscription_status != Tenant.SubscriptionStatus.ACTIVE,
        })


class PublicConfigurationView(APIView):
    """Public, unauthenticated platform configuration for signup/landing.

    Exposes the signup gate, available subscription plans and the reference
    data (countries / facility types) the signup form needs.
    """
    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    def get(self, request):
        _ensure_public_schema()
        signups_open = _bool_setting(_get_system_setting('allow_new_signups', 'true'))
        configured_payment_method = _get_system_setting('subscription_payment_method', 'paystack')
        plans = SubscriptionPlan.objects.filter(is_active=True).order_by('display_order', 'price_monthly')
        countries = Country.objects.filter(is_active=True).order_by('name')
        facility_types = FacilityType.objects.all().order_by('name')
        return Response({
            'allow_new_signups': signups_open,
            'subscription_plans': [
                {
                    'id': p.id, 'name': p.name, 'code': p.code,
                    'price_monthly': p.price_monthly, 'price_quarterly': p.price_quarterly,
                    'price_yearly': p.price_yearly, 'currency': p.currency,
                    'max_users': p.max_users, 'max_patients': p.max_patients,
                    'is_default': p.is_default, 'trial_period_days': p.trial_period_days,
                } for p in plans
            ],
            'countries': [
                {'id': c.id, 'name': c.name, 'code': c.code,
                 'phone_code': c.phone_code, 'currency': c.currency} for c in countries
            ],
            'facility_types': [
                {'id': f.id, 'name': f.name, 'code': f.code, 'description': f.description}
                for f in facility_types
            ],
            'payment_methods': [configured_payment_method] if (
                (configured_payment_method == 'paystack' and payment_setting_configured('paystack_secret_key'))
                or (configured_payment_method == 'paypal' and payment_setting_configured('paypal_client_id') and payment_setting_configured('paypal_client_secret'))
            ) else [],
            'default_payment_method': configured_payment_method if (
                (configured_payment_method == 'paystack' and payment_setting_configured('paystack_secret_key'))
                or (configured_payment_method == 'paypal' and payment_setting_configured('paypal_client_id') and payment_setting_configured('paypal_client_secret'))
            ) else '',
        })



