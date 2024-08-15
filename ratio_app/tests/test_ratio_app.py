# Copyright (c) 2024, Artist Influence Development Team
# All rights reserved.
import json

import pytest
from flask import url_for

from ..campaign import Campaign
from ..main import User, app, bcrypt, users


@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as client:
        with app.app_context():
            yield client


@pytest.fixture
def init_db():
    # Initialize a mock database
    users.clear()
    hashed_password = bcrypt.generate_password_hash("password").decode("utf-8")
    users["1"] = User(id="1", username="testuser", password=hashed_password)


def test_register(client):
    response = client.post(
        "/register",
        data={"username": "newuser", "password": "newpassword"},
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert b"Registration successful. Please log in." in response.data


def test_login(client, init_db):
    response = client.post(
        "/login",
        data={"username": "testuser", "password": "password"},
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert b"Login successful." in response.data


def test_login_invalid(client, init_db):
    response = client.post(
        "/login",
        data={"username": "testuser", "password": "wrongpassword"},
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert b"Invalid username or password." in response.data


def test_logout(client, init_db):
    client.post(
        "/login",
        data={"username": "testuser", "password": "password"},
        follow_redirects=True,
    )
    response = client.get("/logout", follow_redirects=True)
    assert response.status_code == 200
    assert b"You have been logged out." in response.data


def test_create_campaign(client, init_db):
    client.post(
        "/login",
        data={"username": "testuser", "password": "password"},
        follow_redirects=True,
    )
    response = client.post(
        "/create_campaign",
        data={
            "youtube_url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            "channel_id": "UC38IQsAvIsxxjztdMZQtwHA",
            "genre": "Pop",
            "comments_sheet": "https://docs.google.com/spreadsheets/d/testsheet",
            "wait_time": "10",
        },
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert b"Campaign created and running!" in response.data


def test_export_campaigns(client, init_db):
    client.post(
        "/login",
        data={"username": "testuser", "password": "password"},
        follow_redirects=True,
    )
    response = client.get("/export_campaigns")
    assert response.status_code == 200
    assert (
        response.headers["Content-Disposition"]
        == "attachment; filename=campaigns_report.csv"
    )
