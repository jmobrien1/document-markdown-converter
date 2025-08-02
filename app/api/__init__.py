from .routes import api
from app.decorators import api_key_required

# Re-export for backward compatibility
__all__ = ['api', 'api_key_required'] 