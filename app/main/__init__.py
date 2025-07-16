# app/main/__init__.py
# This file makes the 'main' directory a Python package.
# It also defines the 'main' blueprint.

from flask import Blueprint

# A Blueprint is a way to organize a group of related views and other code.
# Rather than registering views and other code directly with an application,
# they are registered with a blueprint. Then the blueprint is registered with
# the application when it is available in the factory function.
main = Blueprint('main', __name__)

# Importing routes at the end to avoid circular dependencies
from . import routes
