"""
JWT Middleware - Placeholder implementation
"""

JWT_EXPIRATION_MINUTES = 60

from functools import wraps

def enforce_rate_limit(max_requests=10, window_minutes=1):
    """Rate limiting decorator placeholder - no enforcement"""
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            return await func(*args, **kwargs)
        return wrapper
    return decorator

async def get_current_user():
    """Get current user placeholder - returns test user"""
    return {"username": "test_user", "role": "user"}
