
# Hotcalls API - Baseline.

To be extended as project progresses. In the end there should be a complete and valid API documentation here

## Authentication & Verification

Email based login. Email verification required for registration. 

### Authentication flow
1. **Registration**: POST to `/api/auth/register/` with email, password, name, phone number
2. **Email Verification**: User receives email with verification link
3. **Verify Email**: Click link or use `/api/auth/verify-email/{token}/`
4. **Login**: POST to `/api/auth/login/` with email and password
5. **Access APIs**: Use token authentication for protected endpoints

Resend of authentication email is possible, if needed. Verification tokens have expiration time

---

## User Roles & Permissions

### User Role Hierarchy
| Role | Level | Description                          |
|------|--------|--------------------------------------|
| **Regular User** | `is_authenticated=True` | Standard user                        |
| **Staff Member** | `is_staff=True` | System staff                         |
| **Superuser** | `is_superuser=True` | Admin - no email verification needed |

Each level of user is required to have an email. 

### Authentication Methods
- **Token Authentication**: Login via `/api/auth/login/` then use `Authorization: Token <token>`
- **Email Verification Required**: Must verify email before first login

---

## Permission Matrix

### Authentication API (`/api/auth/`)
| Operation | Permission | Email Verification | Description |
|-----------|------------|-------------------|-------------|
| **Register** | Public | Not required | Create account, sends verification email |
| **Verify Email** | Public | Completes verification | Verify email with token from email |
| **Login** | Public | Required | Login with email/password |
| **Logout** | Authenticated | Required | Clear user session |
| **Profile** | Authenticated | Required | Get current user profile |
| **Resend Verification** | Public | For unverified emails | Resend verification email |

### User Management API (`/api/users/`)
| Operation | Regular User      | Staff     | Superuser |
|-----------|-------------------|-----------|-----------|
| **View Users** | Own profile       | All users | All users |
| **Create User** | Use auth/register | Any user  | Any user |
| **Edit User** | Own profile       | Any user  | Any user |
| **Delete User** | Own profile       | ?         | Any user |

### Other APIs (`/api/workspaces/`, `/api/agents/`, etc.)
- **All protected APIs require**: Authentication + Email Verification
- **No verification = No access**: Unverified users cannot use any protected endpoints

---

## Authentication Error Responses

***TO BE DONE. Following this pattern***

### XXX Error
```json
{
  "detail": "information message"
}
```
---


