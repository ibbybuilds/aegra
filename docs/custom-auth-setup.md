# Custom JWT Authentication Setup

## Overview

This document explains the custom JWT authentication setup for the Aegra agent server. The authentication system validates JWT tokens sent from the frontend LMS application and decodes them using a shared secret.

## Architecture

```
┌─────────────┐                    ┌──────────────┐
│   Frontend  │  JWT Token         │   Backend    │
│  (Next.js)  │ ─────────────────► │   (Aegra)    │
│             │                    │              │
│  - Creates  │                    │  - Validates │
│    token    │                    │    token     │
│  - Sends in │                    │  - Decodes   │
│    headers  │                    │    user info │
└─────────────┘                    └──────────────┘
                                          │
                                          ▼
                                   ┌──────────────┐
                                   │  LangGraph   │
                                   │   Service    │
                                   │              │
                                   │ User Context │
                                   └──────────────┘
```

## Configuration

### Backend (.env)

```bash
# Authentication type
AUTH_TYPE=custom  # Use custom JWT authentication

# JWT Secret (must match frontend)
LMS_JWT_SECRET=qwertyuiasdfghjzxcvbn
```

### Frontend (.env)

```bash
# Chat API endpoint
NEXT_PUBLIC_CHAT_API_URL=http://127.0.0.1:8000
```

## How It Works

### 1. Frontend Authentication Flow

When a user logs in to the LMS:

1. User provides credentials (email/password)
2. LMS backend validates credentials
3. LMS backend creates JWT token with user information
4. Token is stored in cookies and used for API calls

**Frontend Code (AuthContext.js)**:

```javascript
const client = new Client({
  apiUrl: process.env.NEXT_PUBLIC_CHAT_API_URL,
  defaultHeaders: {
    Authorization: `Bearer ${accessToken}`,
  },
});
```

### 2. Backend Token Validation

When the backend receives a request:

1. **Extract Token**: Gets token from `Authorization: Bearer <token>` header
2. **Decode Token**: Uses `LMS_JWT_SECRET` to decode and validate
3. **Extract User Info**: Pulls user details from token payload
4. **Create User Context**: Makes user info available to LangGraph

**Backend Code (auth.py)**:

```python
payload = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])

return {
    "identity": str(user_id),
    "display_name": name or email,
    "email": email,
    "role": role,
    "permissions": [role] if role else [],
    "is_authenticated": True,
}
```

## JWT Token Structure

The token payload includes:

```json
{
  "userId": "unique-user-id",
  "email": "user@example.com",
  "name": "User Name",
  "role": "student",
  "onboardingComplete": true,
  "onboardingSkipped": false,
  "verified": true,
  "iat": 1234567890,
  "exp": 1234571490
}
```

## User Context in LangGraph

Once authenticated, user information is available in the LangGraph context:

```python
# Access user info in graph nodes
user = ctx.user
user_id = user.identity
user_email = user.email
user_role = user.role
```

## Authorization

The `authorize` handler applies user-scoped access control:

```python
@auth.on
async def authorize(ctx: Auth.types.AuthContext, value: dict[str, Any]) -> dict[str, Any]:
    user_id = ctx.user.identity
    owner_filter = {"owner": user_id}

    # Add owner to metadata
    metadata = value.setdefault("metadata", {})
    metadata.update(owner_filter)

    # Return filter for queries
    return owner_filter
```

This ensures:

- Users can only access their own threads, assistants, and runs
- All created resources are automatically tagged with the owner
- Database queries are filtered by owner

## Testing

### 1. Start the Backend Server

```bash
cd aegra
python run_server.py
```

### 2. Run Authentication Tests

```bash
python test_custom_auth.py
```

This will test:

- ✅ Valid token authentication
- ✅ Invalid token rejection
- ✅ Expired token rejection
- ✅ Thread creation with authentication
- ✅ Assistant listing with authentication

### 3. Test from Frontend

The frontend automatically includes the JWT token in all requests to the LangGraph client when the user is authenticated.

```javascript
// Token is automatically included
const thread = await langGraphClient.threads.create();
```

## Security Considerations

### Secret Management

- **DO NOT** commit `LMS_JWT_SECRET` to version control
- Use different secrets for development and production
- Rotate secrets periodically

### Token Validation

The system validates:

- ✅ Token signature (prevents tampering)
- ✅ Token expiration (prevents replay attacks)
- ✅ Required claims (userId, email, etc.)

### HTTPS in Production

Always use HTTPS in production:

```bash
NEXT_PUBLIC_CHAT_API_URL=https://your-production-domain.com
```

## Troubleshooting

### "Authorization header required"

**Problem**: No token sent in request

**Solution**: Ensure frontend is authenticated and token is in cookies

### "Invalid authentication token"

**Problem**: Token signature validation failed

**Solution**: Check that `LMS_JWT_SECRET` matches between frontend and backend

### "Token has expired"

**Problem**: Token lifetime exceeded

**Solution**: User needs to login again. Frontend should handle token refresh.

### "Invalid token: missing user ID"

**Problem**: Token payload missing required fields

**Solution**: Ensure frontend creates tokens with all required claims

## Environment Variables Summary

| Variable                   | Location | Required | Description                   |
| -------------------------- | -------- | -------- | ----------------------------- |
| `AUTH_TYPE`                | Backend  | Yes      | Set to `custom` for JWT auth  |
| `LMS_JWT_SECRET`           | Backend  | Yes      | Secret key for JWT validation |
| `NEXT_PUBLIC_CHAT_API_URL` | Frontend | Yes      | Backend API endpoint          |

## Example Integration

### Creating a Thread

```javascript
// Frontend
const { langGraphClient } = useAuth();

const thread = await langGraphClient.threads.create();
// Token is automatically included in headers
```

### Running an Agent

```javascript
// Frontend
const streamResponse = langGraphClient.runs.stream(threadId, assistantId, {
  input: { messages: [{ role: "user", content: "Hello!" }] },
});

for await (const chunk of streamResponse) {
  console.log(chunk);
}
```

### Accessing User Context in Graph

```python
# Backend (in graph node)
from langgraph.prebuilt import create_react_agent

def my_node(state, config):
    # Get authenticated user from config
    user_id = config.get("configurable", {}).get("user_id")
    # Use user_id for personalization
    return state
```

## Additional Resources

- [LangGraph Authentication Docs](https://langchain-ai.github.io/langgraph/reference/auth/)
- [JWT.io - Token Debugger](https://jwt.io/)
- [PyJWT Documentation](https://pyjwt.readthedocs.io/)
