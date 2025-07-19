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
        mrr = premium_users * 9.99  # Monthly recurring revenue
        
        # Customer lifetime value estimation
        # Assuming average subscription length of 12 months
        clv = mrr * 12
        
        return {
            'mrr': mrr,
            'arr': mrr * 12,  # Annual recurring revenue
            'clv': clv,
            'premium_users': premium_users
        }
    
    @staticmethod
    def get_usage_patterns():
        """Analyze conversion patterns and popular formats"""
        thirty_days_ago = datetime.utcnow() - timedelta(days=30)
        
        # Most popular file types
        file_types = db.session.query(
            Conversion.file_type, 
            db.func.count(Conversion.id).label('count')
        ).filter(
            Conversion.created_at >= thirty_days_ago
        ).group_by(Conversion.file_type).all()
        
        # Pro vs standard usage
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
    
    @staticmethod
    def get_conversion_health():
        """Monitor conversion success rates and failure patterns"""
        last_24h = datetime.utcnow() - timedelta(hours=24)
        last_7d = datetime.utcnow() - timedelta(days=7)
        
        # Recent conversion stats
        recent_total = Conversion.query.filter(Conversion.created_at >= last_24h).count()
        recent_failed = Conversion.query.filter(
            Conversion.created_at >= last_24h,
            Conversion.status == 'failed'
        ).count()
        
        # Weekly trends
        weekly_total = Conversion.query.filter(Conversion.created_at >= last_7d).count()
        weekly_failed = Conversion.query.filter(
            Conversion.created_at >= last_7d,
            Conversion.status == 'failed'
        ).count()
        
        # Common failure reasons
        failure_reasons = db.session.query(
            Conversion.error_message,
            db.func.count(Conversion.id).label('count')
        ).filter(
            Conversion.status == 'failed',
            Conversion.created_at >= last_7d
        ).group_by(Conversion.error_message).all()
        
        return {
            'daily_success_rate': ((recent_total - recent_failed) / recent_total * 100) if recent_total > 0 else 100,
            'weekly_success_rate': ((weekly_total - weekly_failed) / weekly_total * 100) if weekly_total > 0 else 100,
            'recent_failures': recent_failed,
            'common_errors': dict(failure_reasons[:5])  # Top 5 error types
        }