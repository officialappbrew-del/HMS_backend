# Support Tickets Documentation

## Overview

The Support Ticket system allows tenants to submit and track technical issues or support requests. Super Admins can manage all tickets across the platform, while tenant users can only view and create tickets for their own tenant.

---

## Backend Implementation

### Model

**File:** `tenants/models.py`

```python
class SupportTicket(BaseModel):
    tenant = models.ForeignKey('Tenant', on_delete=models.CASCADE, related_name='support_tickets')
    subject = models.CharField(max_length=200)
    description = models.TextField()
    priority = models.CharField(max_length=20, choices=Priority.choices, default=Priority.MEDIUM)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.OPEN)
    created_by_name = models.CharField(max_length=100)
    created_by_email = models.EmailField()
    created_by_role = models.CharField(max_length=50)
    assigned_to = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolution_notes = models.TextField(blank=True)
```

### Endpoints

#### Super Admin Endpoints

| Method | URL | Description |
|--------|-----|-------------|
| GET | `/api/v1/superadmin/support-tickets/` | List all tickets (filterable by tenant, status, priority) |
| POST | `/api/v1/superadmin/support-tickets/` | Create a new ticket |
| GET | `/api/v1/superadmin/support-tickets/{id}/` | Get ticket details |
| PUT | `/api/v1/superadmin/support-tickets/{id}/` | Update ticket (partial) |
| DELETE | `/api/v1/superadmin/support-tickets/{id}/` | Delete ticket |

**Views:** `superadmin/views.py` - `SupportTicketListView`, `SupportTicketDetailView`
**Permissions:** `IsSuperAdmin`
**Serializer:** `superadmin/serializers.py` - `SupportTicketSerializer`

#### Tenant Endpoints

| Method | URL | Description |
|--------|-----|-------------|
| GET | `/api/v1/tenants/support-tickets/` | List tickets for current tenant |
| POST | `/api/v1/tenants/support-tickets/` | Create a new ticket |
| GET | `/api/v1/tenants/support-tickets/{id}/` | Get ticket details |
| PATCH | `/api/v1/tenants/support-tickets/{id}/` | Update ticket (partial) |

**View:** `tenants/views.py` - `TenantSupportTicketViewSet`
**Permissions:** `IsAuthenticated` (tenant-scoped)
**Serializer:** `superadmin/serializers.py` - `SupportTicketSerializer`

### URL Configuration

**Super Admin:** `superadmin/urls.py`
```python
path('support-tickets/', SupportTicketListView.as_view(), name='superadmin-support-tickets'),
path('support-tickets/<int:ticket_id>/', SupportTicketDetailView.as_view(), name='superadmin-support-ticket-detail'),
```

**Tenant:** `tenants/urls.py`
```python
router.register(r'support-tickets', TenantSupportTicketViewSet, basename='tenant-support-ticket')
```

---

## Frontend Implementation

### Super Admin Page

**File:** `src/pages/SuperAdmin/SupportTickets.jsx`

Features:
- List all support tickets with search, status, priority, and tenant filters
- Create new tickets with tenant selection, subject, description, priority, and creator details
- View ticket details in a modal
- Update ticket status: Open → In Progress → Resolved → Closed
- Add resolution notes when marking as resolved
- Pagination

**API Calls:** `src/utils/superAdminApi.js`
- `getSupportTickets(params)`
- `getSupportTicket(ticketId)`
- `updateSupportTicket(ticketId, data)`
- `deleteSupportTicket(ticketId)`
- `createSupportTicket(data)`

### Tenant Page

**File:** `src/pages/TenantSupportTickets.jsx`

Features:
- List tickets for the current tenant
- Create new tickets (tenant is auto-assigned from logged-in user)
- View ticket details
- Update ticket status
- Search and filter by status

**API Calls:** `src/utils/api.js`
- `getSupportTickets(params)`
- `getSupportTicket(ticketId)`
- `createSupportTicket(data)`
- `updateSupportTicket(ticketId, data)`

---

## How to Use

### For Tenants

1. **Navigate to Support Tickets**
   - Go to the tenant dashboard
   - Click on "Support Tickets" or navigate to `/support-tickets`

2. **Create a New Ticket**
   - Click the "New Ticket" button
   - Fill in the form:
     - **Subject**: Brief description of the issue
     - **Description**: Detailed explanation of the problem
     - **Priority**: Choose Low, Medium, High, or Critical
     - **Creator Role**: Your role in the organization
     - **Creator Name**: Your full name
     - **Creator Email**: Your email address
   - Click "Create Ticket"

3. **View Tickets**
   - The ticket list shows all your tenant's tickets
   - Use the search bar to find specific tickets
   - Filter by status (Open, In Progress, Resolved, Closed)

4. **Track Ticket Status**
   - Click the eye icon to view ticket details
   - See the current status and any resolution notes
   - Statuses:
     - **Open**: Ticket has been submitted
     - **In Progress**: Support team is working on it
     - **Resolved**: Issue has been resolved
     - **Closed**: Ticket has been closed

### For Super Admins

1. **Navigate to Support Tickets**
   - Go to the Super Admin dashboard
   - Click on "Support" or navigate to `/support`

2. **View All Tickets**
   - See all tickets across all tenants
   - Filter by:
     - **Tenant**: Filter tickets for a specific tenant
     - **Status**: Filter by Open, In Progress, Resolved, or Closed
     - **Priority**: Filter by Low, Medium, High, or Critical
     - **Search**: Search by subject or tenant name

3. **Create a Ticket on Behalf of a Tenant**
   - Click "New Ticket"
   - Select the tenant
   - Fill in the ticket details
   - Click "Create Ticket"

4. **Manage Tickets**
   - Click the eye icon to view ticket details
   - Update the status:
     - **Start Progress**: Mark as In Progress
     - **Mark Resolved**: Add resolution notes and mark as resolved
     - **Close Ticket**: Close the ticket
   - Delete tickets if necessary

5. **Ticket Priority Guide**
   - **Low**: Minor issues, no immediate impact
   - **Medium**: Standard support requests
   - **High**: Issues affecting operations
   - **Critical**: System down or data loss

---

## Status Workflow

```
Open → In Progress → Resolved → Closed
```

- **Open**: Initial state when ticket is created
- **In Progress**: Support team is actively working on the ticket
- **Resolved**: Issue has been fixed, resolution notes added
- **Closed**: Ticket is complete and archived

---

## API Reference

### Create Ticket
```http
POST /api/v1/tenants/support-tickets/
Content-Type: application/json

{
  "subject": "Login page not loading",
  "description": "Users are unable to log in to the system...",
  "priority": "high",
  "created_by_name": "John Doe",
  "created_by_email": "john@example.com",
  "created_by_role": "tenant_admin"
}
```

### List Tickets
```http
GET /api/v1/tenants/support-tickets/?status=open&page_size=20
```

### Get Ticket
```http
GET /api/v1/tenants/support-tickets/{id}/
```

### Update Ticket
```http
PATCH /api/v1/tenants/support-tickets/{id}/
Content-Type: application/json

{
  "status": "resolved",
  "resolution_notes": "Fixed by clearing cache..."
}
```

---

## Notes

- Tenant users can only see tickets for their own tenant
- Super Admins can see and manage all tickets
- The `tenant` field is automatically set for tenant-created tickets
- `created_by_name`, `created_by_email`, and `created_by_role` are auto-populated for tenant users
- Tickets are ordered by creation date (newest first)
- The `resolved_at` timestamp is automatically set when status changes to `resolved`
