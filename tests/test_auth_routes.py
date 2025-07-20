import pytest
from flask import url_for
from app.models import User


def test_user_status_unauthenticated(client):
    response = client.get('/user-status')
    assert response.status_code == 200
    data = response.get_json()
    assert data['authenticated'] is False


def test_user_status_authenticated(client, db):
    # Create a user
    email = 'testuser@example.com'
    password = 'testpassword'
    user = User(email=email)
    user.password = password
    db.session.add(user)
    db.session.commit()

    # Log in the user
    response = client.post('/login', data={
        'email': email,
        'password': password
    }, follow_redirects=True)
    assert response.status_code == 200

    # Check user status
    response = client.get('/user-status')
    assert response.status_code == 200
    data = response.get_json()
    assert data['authenticated'] is True
    assert data['email'] == email 