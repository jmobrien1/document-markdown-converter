# Lazy import to avoid circular dependencies
def get_api_blueprint():
    from .routes import api
    return api

# Re-export for backward compatibility
from app.decorators import api_key_required
__all__ = ['get_api_blueprint', 'api_key_required'] 