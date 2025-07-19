# app/analytics.py
# Data analytics logic only - NO ROUTES

from datetime import datetime, timedelta
from flask import current_app
from .models import User, Conversion, AnonymousUsage
from . import db

class Analytics:
    @staticmethod
    def get_conversion_funnel():
        """Track the conversion funnel from anonymous to paid users"""
        total_anonymous = AnonymousUsage.query.count()
        total_registered = User.query.count()
        total_premium = User.query.filter_by(is_premium=True).count()
        
        return {
            'anonymous_users': total_anonymous,
            'registered_users': total_registered,
            'premium_users': total_premium,
            'registration_rate': (total_registered / total_anonymous * 100) if total_anonymous > 0 else 0,
            'premium_conversion_rate': (total_premium / total_registered * 100) if total_registered > 0 else 0
        }
    
    @staticmethod
    def get_revenue_metrics():
        """Calculate key revenue metrics"""
        premium_users = User.query.filter_by(is_premium=True).count()
        mrr = premium_users * 9.99
        
        return {
            'mrr': mrr,
            'arr': mrr * 12,
            'clv': mrr * 12,
            'premium_users': premium_users
        }
    
    @staticmethod
    def get_usage_patterns():
        """Analyze conversion patterns and popular formats"""
        thirty_days_ago = datetime.utcnow() - timedelta(days=30)
        
        file_types = db.session.query(
            Conversion.file_type, 
            db.func.count(Conversion.id).label('count')
        ).filter(
            Conversion.created_at >= thirty_days_ago
        ).group_by(Conversion.file_type).all()
        
        conversion_types = db.session.query(
            Conversion.conversion_type,
            db.func.count(Conversion.id).label('count')
        ).filter(
            Conversion.created_at >= thirty_days_ago
        ).group_by(Conversion.conversion_type).all()
        
        return {
            'popular_file_types': dict(file_types),
            'conversion_type_usage': dict(conversion_types)
        }
