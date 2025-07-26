# HotCalls - AI Agent Call Management System

A comprehensive Django-based API system for managing AI agents, call logs, leads, workspaces, and calendar integrations.

## API Architecture

The system is organized into 7 main API modules under `core/management_api/`:

### 1. User Management API (`/api/users/`)
- **User CRUD**: Complete user management with permissions
- **Blacklist Management**: User blacklisting functionality
- **Endpoints**:
  - `GET/POST /users/` - List/Create users
  - `GET/PUT/PATCH/DELETE /users/{id}/` - User operations
  - `GET/PATCH /users/me/` - Current user profile
  - `PATCH /users/{id}/change_status/` - Change user status
  - `GET/POST/PUT/PATCH/DELETE /blacklist/` - Blacklist operations

### 2. Subscription Management API (`/api/subscriptions/`)
- **Plan Management**: Subscription plans and features
- **Feature Assignment**: Plan-feature relationships
- **Endpoints**:
  - `GET/POST/PUT/PATCH/DELETE /plans/` - Plan operations
  - `GET /plans/{id}/features/` - Get plan features
  - `POST /plans/{id}/add_feature/` - Assign feature to plan
  - `DELETE /plans/{id}/remove_feature/` - Remove feature from plan
  - `GET/POST/PUT/PATCH/DELETE /features/` - Feature operations
  - `GET/POST/PUT/PATCH/DELETE /plan-features/` - Direct plan-feature management

### 3. Workspace Management API (`/api/workspaces/`)
- **Workspace CRUD**: Workspace management
- **User Assignment**: Add/remove users from workspaces
- **Endpoints**:
  - `GET/POST/PUT/PATCH/DELETE /workspaces/` - Workspace operations
  - `GET /workspaces/{id}/users/` - Get workspace users
  - `POST /workspaces/{id}/add_users/` - Add users to workspace
  - `POST /workspaces/{id}/remove_users/` - Remove users from workspace
  - `GET /workspaces/{id}/stats/` - Workspace statistics

### 4. Agent Management API (`/api/agents/`)
- **Agent CRUD**: AI agent management
- **Phone Number Management**: Phone number assignment
- **Endpoints**:
  - `GET/POST/PUT/PATCH/DELETE /agents/` - Agent operations
  - `GET /agents/{id}/phone_numbers/` - Get agent phone numbers
  - `POST /agents/{id}/assign_phone_numbers/` - Assign phone numbers
  - `POST /agents/{id}/remove_phone_numbers/` - Remove phone numbers
  - `GET /agents/{id}/config/` - Get agent configuration
  - `GET/POST/PUT/PATCH/DELETE /phone-numbers/` - Phone number operations

### 5. Lead Management API (`/api/leads/`)
- **Lead CRUD**: Lead management with metadata
- **Bulk Operations**: Bulk lead creation
- **Call History**: Lead call tracking
- **Endpoints**:
  - `GET/POST/PUT/PATCH/DELETE /leads/` - Lead operations
  - `POST /leads/bulk_create/` - Bulk create leads
  - `PATCH /leads/{id}/update_metadata/` - Update lead metadata
  - `GET /leads/{id}/call_history/` - Get lead call history
  - `GET /leads/stats/` - Lead statistics

### 6. Call Management API (`/api/calls/`)
- **Call Log CRUD**: Call tracking and management
- **Analytics**: Call statistics and analytics
- **Endpoints**:
  - `GET/POST/PUT/PATCH/DELETE /call-logs/` - Call log operations
  - `GET /call-logs/analytics/` - Call analytics
  - `GET /call-logs/daily_stats/` - Daily call statistics
  - `GET /call-logs/duration_distribution/` - Call duration distribution

### 7. Calendar Management API (`/api/calendars/`)
- **Calendar Integration**: Google/Outlook calendar support
- **Configuration Management**: Calendar scheduling settings
- **Availability Checking**: Time slot availability
- **Endpoints**:
  - `GET/POST/PUT/PATCH/DELETE /calendars/` - Calendar operations
  - `GET /calendars/{id}/configurations/` - Get calendar configurations
  - `POST /calendars/{id}/test_connection/` - Test calendar connection
  - `GET/POST/PUT/PATCH/DELETE /calendar-configurations/` - Configuration operations
  - `POST /calendar-configurations/{id}/check_availability/` - Check availability

## Features

### 🔐 **Authentication & Permissions**
- User-based authentication
- Role-based permissions (Regular users, Staff, Superusers)
- Object-level permissions
- Workspace-based access control

### 🔍 **Advanced Filtering & Search**
- **Global Search**: Search across multiple fields
- **Date Range Filtering**: Created/updated date filters
- **Custom Filters**: Domain-specific filters for each model
- **Sorting**: Configurable ordering on multiple fields

### 📊 **Analytics & Reporting**
- Call analytics and statistics
- Lead management metrics
- Workspace utilization stats
- Daily/duration-based reporting

### 🚀 **Bulk Operations**
- Bulk lead creation
- Bulk user assignments
- Bulk phone number management

### 📅 **Calendar Integration**
- Google Calendar support
- Outlook Calendar support
- Availability checking
- Meeting scheduling

## Setup Instructions

### 1. Activate Virtual Environment
```bash
# Activate the virtual environment
source venv/bin/activate  # On macOS/Linux
# or
venv\Scripts\activate     # On Windows
```

### 2. Install Dependencies
```bash
pip install -r requirements.txt
```

### 3. Database Setup
```bash
# Create and apply migrations
python manage.py makemigrations
python manage.py migrate

# Create superuser (optional)
python manage.py createsuperuser
```

### 4. Run Development Server
```bash
python manage.py runserver
```

## API Documentation

### 📚 **Swagger Documentation**
- **Swagger UI**: http://localhost:8000/api/docs/
- **ReDoc**: http://localhost:8000/api/redoc/
- **OpenAPI Schema**: http://localhost:8000/api/schema/

### 🔧 **API Features**
- **Pagination**: 20 items per page by default
- **Response Format**: JSON with consistent structure
- **Error Handling**: Detailed error messages
- **No Versioning**: Clean, simple URL structure

### 📝 **Request/Response Examples**

#### Create a User
```bash
POST /api/users/users/
{
  "username": "john_doe",
  "first_name": "John",
  "last_name": "Doe",
  "email": "john@example.com",
  "phone": "+1234567890",
  "password": "securepassword123"
}
```

#### Create a Workspace
```bash
POST /api/workspaces/workspaces/
{
  "workspace_name": "Marketing Team"
}
```

#### Create an Agent
```bash
POST /api/agents/agents/
{
  "workspace": "workspace-uuid",
  "greeting": "Hello! How can I help you today?",
  "voice": "en-US-Wavenet-D",
  "language": "en-US",
  "retry_interval": 30,
  "workdays": ["monday", "tuesday", "wednesday", "thursday", "friday"],
  "call_from": "09:00:00",
  "call_to": "17:00:00",
  "character": "Friendly and professional customer service agent"
}
```

## Testing the APIs

### 1. **Using Swagger UI**
Visit http://localhost:8000/api/docs/ for interactive API testing

### 2. **Using curl**
```bash
# Get all users (requires authentication)
curl -X GET "http://localhost:8000/api/users/users/" \
     -H "Authorization: Basic <base64-encoded-credentials>"

# Create a lead
curl -X POST "http://localhost:8000/api/leads/leads/" \
     -H "Content-Type: application/json" \
     -d '{"name": "Jane Smith", "email": "jane@example.com", "phone": "+1987654321"}'
```

### 3. **Authentication**
The APIs use session-based authentication. You can:
- Use Django admin login at `/admin/`
- Create API tokens for programmatic access
- Use basic authentication for testing

## Technology Stack

- **Backend**: Django 5.0+ with Django REST Framework
- **Documentation**: drf-spectacular (OpenAPI 3.0)
- **Filtering**: django-filter
- **CORS**: django-cors-headers
- **Database**: SQLite (development) / PostgreSQL (production)

## Security Features

- **CSRF Protection**: Enabled for web requests
- **CORS Configuration**: Configured for frontend development
- **Authentication Required**: All endpoints require authentication
- **Permission Classes**: Custom permissions for each domain
- **Input Validation**: Comprehensive serializer validation

The API is now fully implemented with complete CRUD operations, advanced filtering, analytics, and comprehensive Swagger documentation!
