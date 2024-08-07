# Copyright (c) 2024, Artist Influence Development Team
# All rights reserved.

import json
import logging as log
import os
import threading
import uuid

import pandas as pd
from dotenv import load_dotenv
from flask import (
    Flask,
    flash,
    redirect,
    render_template,
    request,
    send_file,
    send_from_directory,
    session,
    url_for,
)
from flask_bcrypt import Bcrypt
from flask_login import (
    LoginManager,
    UserMixin,
    current_user,
    login_required,
    login_user,
    logout_user,
)

from campaign import Campaign, YoutubeRatioCalc
from jingle_smm import JingleSMM

load_dotenv()
API_KEY = os.getenv("YOUTUBE_API_KEY")


# Set up logging
logger = log.getLogger(__name__)
logger.setLevel(log.INFO)
handler = log.StreamHandler()
handler.setFormatter(log.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
logger.addHandler(handler)


app = Flask(__name__, template_folder="templates")
app.secret_key = (
    "your_secret_key"  # You should use a secure and random secret key for production
)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"

bcrypt = Bcrypt(app)


# Mock database
users = {}


class User(UserMixin):
    def __init__(self, id, username, password):
        self.id = id
        self.username = username
        self.password = password


# User loader function for Flask-Login
@login_manager.user_loader
def load_user(user_id):
    return users.get(user_id)


# Global dictionary to store campaign threads
campaign_threads = {}


campaigns = pd.DataFrame(
    columns=[
        "Video Title",
        "Video Link",
        "Video ID",
        "Genre",
        "Comments Sheet URL",
        "Wait Time",
        "Status",
        "Likes",
        "Comments",
        "Views",
    ]
)


def load_csv(file_path):
    return pd.read_csv(file_path)


def process_campaign(comments, video_id, service=1751):
    api = JingleSMM()
    # Add order
    order = api.order(
        {
            "service": service,
            "link": f"https://www.youtube.com/watch?v={video_id}",
            "comments": comments,
        }
    )
    print(order, "order")
    if "error" in order:
        print("Error: " + order["error"])
    else:
        print(order)
    # Check order status
    status = api.status(order["order"])
    return status, order["order"]


@app.route("/favicon.ico")
def favicon():
    return send_from_directory(
        os.path.join(app.root_path, "./static/AI_Logo_2024--r.png"),
        "favicon.ico",
        mimetype="image/vnd.microsoft.icon",
    )


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]
        hashed_password = bcrypt.generate_password_hash(password).decode("utf-8")
        user_id = str(len(users) + 1)
        users[user_id] = User(user_id, username, hashed_password)
        flash("Registration successful. Please log in.", "success")
        return redirect(url_for("login"))
    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]
        user = next((u for u in users.values() if u.username == username), None)
        if user and bcrypt.check_password_hash(user.password, password):
            login_user(user)
            flash("Login successful.", "success")
            return redirect(url_for("index"))
        else:
            flash("Invalid username or password.", "danger")
    return render_template("login.html")


@app.route("/logout")
@login_required
def logout():
    logout_user()
    flash("You have been logged out.", "success")
    return redirect(url_for("login"))


@app.route("/", methods=["GET", "POST"])
@login_required
def index():
    return render_template(
        "index.html",
        user=current_user,
        campaigns=json.loads(session.get("campaigns", "[]")),
    )


@app.route("/create_campaign", methods=["GET", "POST"])
@login_required
def create_campaign():
    if request.method == "POST":
        video_link = request.form["youtube_url"]
        video_id = video_link.split("v=")[1]
        genre = request.form["genre"]
        comments_sheet = request.form["comments_sheet"]
        wait_time = int(request.form["wait_time"])
        rc = YoutubeRatioCalc(API_KEY, video_id)
        likes, comments, views = rc.get_views_likes_cmnts()
        title = rc.get_video_title()
        if not video_id:
            flash(
                "Please enter a YouTube video link and upload comments first.", "danger"
            )
            return redirect(url_for("index"))

        try:
            campaign_data = {
                "Video Link": video_link,
                "Video Title": title,
                "Video ID": video_id,
                "Genre": genre,
                "Comments Sheet URL": comments_sheet,
                "Wait Time": wait_time,
                "Status": "Running",
                "Likes": likes,
                "Comments": comments,
                "Views": views,
                "Campaign ID": str(uuid.uuid4()),  # Generate a unique campaign ID
            }
            campaign = Campaign(campaign_data, rc, comments_sheet, wait_time)
            # Convert session campaigns to DataFrame, append the new campaign, and save back to session
            campaigns_df = pd.DataFrame(json.loads(session.get("campaigns", "[]")))
            campaigns_df = pd.concat(
                [campaigns_df, pd.DataFrame([campaign_data])], ignore_index=True
            )
            session["campaigns"] = campaigns_df.to_json(orient="records")
            # Start the campaign in a new thread
            flash("Campaign created and running!", "success")
            threading.Thread(
                target=campaign.run, args=(views,)
            ).start()  # Run as a background process
            campaign_thread = threading.Thread(target=campaign.run, args=(views,))
            campaign_thread.start()
            campaign_threads[campaign_data["Campaign ID"]] = (campaign, campaign_thread)
            return redirect(url_for("index"))
        except Exception as e:
            flash(f"An error occurred: {str(e)}", "danger")
        return redirect(url_for("index"))
    flash("Please enter a YouTube video link and upload comments first.", "danger")
    return redirect(url_for("index"))


@app.route("/start_campaign/<campaign_id>", methods=["POST"])
@login_required
def start_campaign(campaign_id):
    campaigns_df = pd.DataFrame(json.loads(session.get("campaigns", "[]")))
    campaign_data = campaigns_df.loc[
        campaigns_df["Campaign ID"] == campaign_id
    ].to_dict(orient="records")[0]
    campaign_data["Status"] = "Running"
    campaigns_df.loc[campaigns_df["Campaign ID"] == campaign_id, "Status"] = "Running"
    session["campaigns"] = campaigns_df.to_json(orient="records")

    # Restart the campaign
    campaign, _ = campaign_threads.get(campaign_id, (None, None))
    if campaign:
        logger.info(f"Restarting campaign {campaign_id}")
        campaign.stop_flag.clear()
        campaign_thread = threading.Thread(
            target=campaign.run, args=(campaign.data["Views"],)
        )
        campaign_thread.start()
        campaign_threads[campaign_id] = (campaign, campaign_thread)

    return redirect(url_for("index"))


def stop_campaign_thread(campaign_id):
    campaign, campaign_thread = campaign_threads.get(campaign_id, (None, None))
    if campaign:
        logger.info(f"Stopping campaign {campaign_id} thread")
        campaign.stop()
        logger.info(f"Waiting for campaign {campaign_id} thread to stop")
        campaign_thread.join()
        logger.info(f"Campaign {campaign_id} thread stopped")


@app.route("/stop_campaign/<campaign_id>", methods=["POST"])
@login_required
def stop_campaign(campaign_id):
    logger.info(f"Stopping campaign {campaign_id}")
    campaigns_df = pd.DataFrame(json.loads(session.get("campaigns", "[]")))
    campaign_data = campaigns_df.loc[
        campaigns_df["Campaign ID"] == campaign_id
    ].to_dict(orient="records")[0]
    campaign_data["Status"] = "Completed"
    campaigns_df.loc[campaigns_df["Campaign ID"] == campaign_id, "Status"] = "Completed"
    session["campaigns"] = campaigns_df.to_json(orient="records")

    # Stop the campaign
    campaign, campaign_thread = campaign_threads.get(campaign_id, (None, None))
    if campaign:
        logger.info(f"Stopping campaign {campaign_id} thread")
        campaign.stop()
        # Stop the campaign asynchronously
        thread = threading.Thread(target=stop_campaign_thread, args=(campaign_id,))
        thread.start()

    return redirect(url_for("index"))


@app.route("/export_campaigns", methods=["GET"])
@login_required
def export():
    campaigns_df = pd.DataFrame(json.loads(session.get("campaigns", "[]")))
    file_path = "campaigns_report.csv"
    campaigns_df.to_csv(file_path, index=False)
    return send_file(file_path, as_attachment=True)


@app.route("/stop", methods=["POST"])
@login_required
def stop():
    for campaign_id, (campaign, campaign_thread) in campaign_threads.items():
        if campaign_thread.is_alive():  # Check if the thread is still running
            campaign.stop()  # Signal the campaign to stop
            # Stop the campaign asynchronously
            thread = threading.Thread(target=stop_campaign_thread, args=(campaign_id,))
            thread.start()
    # Clear the campaign_threads dictionary
    campaign_threads.clear()
    # Update the status of all campaigns in the session
    campaigns_df = pd.DataFrame(json.loads(session.get("campaigns", "[]")))
    campaigns_df["Status"] = "Completed"
    session["campaigns"] = campaigns_df.to_json(orient="records")
    flash("All campaigns stopped!", "success")
    return redirect(url_for("index"))


if __name__ == "__main__":
    app.run(debug=True)
