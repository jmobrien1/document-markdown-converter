# app/__init__.py
# ... (all the previous code in this file remains the same) ...

def create_app(config_name='default'):
    """
    This is the application factory.
    """
    app = Flask(__name__)
    app.config.from_object(config[config_name])
    
    # ... (all the extension initializations remain the same) ...
    
    # Register Blueprints
    from .main import main as main_blueprint
    app.register_blueprint(main_blueprint)

    from .auth import auth as auth_blueprint
    app.register_blueprint(auth_blueprint)

    # User Loader
    from .models import User
    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    # --- ADD THIS AT THE END OF THE FUNCTION ---
    # A custom CLI command to create the database tables
    @app.cli.command("create-db")
    def create_db_command():
        """Runs the SQL CREATE statements to create the tables."""
        db.create_all()
        print("Database tables created.")
    # --- END ADDITION ---

    return app
