# Copyright (c) 2024, Artist Influence Development Team
# All rights reserved.

import logging as log
import os
import threading
import uuid

import numpy as np
import pandas as pd
from dotenv import load_dotenv
from flask import (
    Flask,
    flash,
    jsonify,
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

from google.cloud import storage



load_dotenv()
API_KEY = os.getenv("YOUTUBE_API_KEY")


# Set up logging
logger = log.getLogger(__name__)
logger.setLevel(log.INFO)
handler = log.StreamHandler()
handler.setFormatter(log.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
logger.addHandler(handler)

from flask_sqlalchemy import SQLAlchemy

# Initialize GCP storage client
storage_client = storage.Client()
bucket_name = 'rich-phenomenon-428302-q5.appspot.com'
bucket = storage_client.bucket(bucket_name)

# Update SQLite database path
db_blob_name = 'campaigns.db'
db_file_path = f'/tmp/{db_blob_name}'


# Initialize Flask app and SQLAlchemy
app = Flask(__name__, template_folder="templates")
app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{db_file_path}"
app.config["SQLALCHEMY_ECHO"] = True  # Log SQL queries to the console
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.secret_key = (
    "your_secret_key"  # You should use a secure and random secret key for production
)

db = SQLAlchemy(app)
bcrypt = Bcrypt(app)


login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"

bcrypt = Bcrypt(app)


class CampaignModel(db.Model):
    id = db.Column(db.Integer)
    campaign_id = db.Column(
        db.String(36), unique=True, nullable=False, primary_key=True
    )
    video_title = db.Column(db.String(100), nullable=False)
    video_link = db.Column(db.String(255), nullable=False)
    video_id = db.Column(db.String(50), nullable=False)
    genre = db.Column(db.String(50), nullable=False)
    comments_sheet_url = db.Column(db.String(255), nullable=False)
    wait_time = db.Column(db.Integer, nullable=False)
    status = db.Column(db.String(50), nullable=False)
    likes = db.Column(db.Integer, nullable=True)
    comments = db.Column(db.Integer, nullable=True)
    views = db.Column(db.Integer, nullable=True)
    desired_comments = db.Column(db.Integer, nullable=True)

    def to_dict(self):
        return {
            "Campaign ID": self.campaign_id,
            "Video Title": self.video_title,
            "Video Link": self.video_link,
            "Video ID": self.video_id,
            "Genre": self.genre,
            "Comments Sheet URL": self.comments_sheet_url,
            "Wait Time": self.wait_time,
            "Status": self.status,
            "Likes": self.likes,
            "Comments": self.comments,
            "Views": self.views,
            "Desired Comments": self.desired_comments,
        }


# Mock database
users = {}


class User(UserMixin):
    def __init__(self, id, username, password):
        self.id = id
        self.username = username
        self.password = password

def download_db():
    blob = bucket.blob(db_blob_name)
    blob.download_to_filename(db_file_path)

def upload_db():
    blob = bucket.blob(db_blob_name)
    blob.upload_from_filename(db_file_path)

def save_db_changes():
    save_db_changes()
    upload_db()

@app.before_request
def create_tables():
    app.before_request_funcs[None].remove(create_tables)
    download_db()
    db.create_all()

# User loader function for Flask-Login
@login_manager.user_loader
def load_user(user_id):
    return users.get(user_id)


# Global dictionary to store campaign threads
campaign_threads = {}


def load_csv(file_path):
    return pd.read_csv(file_path)


def process_campaign(comments, video_id, service=440):
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


def stop_campaign_thread(campaign_id):
    try:
        campaign, campaign_thread = campaign_threads.get(campaign_id, (None, None))
        if campaign and campaign_thread.is_alive():
            logger.info(f"Stopping campaign {campaign_id} thread")
            campaign.stop()
            logger.info(f"Waiting for campaign {campaign_id} thread to stop")
            campaign_thread.join()
            logger.info(f"Campaign {campaign_id} thread stopped")
        else:
            logger.info(f"Campaign {campaign_id} thread not found")
    except Exception as e:
        logger.error(f"Error stopping campaign {campaign_id} thread: {e}")
        return False
    return True


def stop_and_clear_all_campaigns(campaign_threads, db, CampaignModel):
    """
    Stops all active campaigns, clears campaign threads, and deletes all campaign records from the database.

    Args:
        campaign_threads (dict): Dictionary storing all active campaign threads.
        db (SQLAlchemy): SQLAlchemy instance to interact with the database.
        CampaignModel (db.Model): The Campaign model representing the campaigns table in the database.
    """
    logger.info("Stopping and clearing all campaigns.")

    # Iterate over all active campaigns and stop them
    for campaign_id, (campaign, campaign_thread) in campaign_threads.items():
        if campaign_thread.is_alive():  # Check if the thread is still running
            campaign.stop()  # Signal the campaign to stop
            logger.info(f"Waiting for campaign {campaign_id} thread to stop.")
            # Stop the campaign asynchronously
            thread = threading.Thread(target=stop_campaign_thread, args=(campaign_id,))
            thread.start()
            logger.info(f"Campaign {campaign_id} has been stopped.")

    # Clear the campaign_threads dictionary
    campaign_threads.clear()

    # Delete all campaigns from the database
    try:
        num_deleted = db.session.query(CampaignModel).delete()
        save_db_changes()
        logger.info(f"Deleted {num_deleted} campaigns from the database.")
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error clearing campaigns from the database: {e}")

    logger.info(
        "All campaigns have been stopped, cleared, and removed from the database."
    )


def start_all_campaigns(campaign_threads, db, CampaignModel):
    """
    Starts all campaigns in the database.

    Args:
        campaign_threads (dict): Dictionary storing all active campaign threads.
        db (SQLAlchemy): SQLAlchemy instance to interact with the database.
        CampaignModel (db.Model): The Campaign model representing the campaigns table in the database.
    """
    logger.info("Starting all campaigns.")
    try:
        # Retrieve all campaigns from the database
        all_campaigns = CampaignModel.query.all()

        # Iterate over all campaigns and start them
        for campaign_data in all_campaigns:
            try:
                rc = YoutubeRatioCalc(API_KEY, campaign_data.video_id)
                rc.get_views_likes_cmnts()
                rc.get_video_title()
                campaign = Campaign(
                    campaign_data.to_dict(),
                    rc,
                    campaign_data.comments_sheet_url,
                    campaign_data.wait_time,
                )
                campaign.data["Status"] = "Running"
                campaign_thread = threading.Thread(
                    target=campaign.run, args=(campaign.data["Views"],)
                )
                campaign_thread.start()
                campaign_threads[campaign_data.campaign_id] = (campaign, campaign_thread)
                campaign_data.status = "Running"
                save_db_changes()
                logger.info(f"Started campaign {campaign_data.campaign_id}")
            except Exception as e:
                logger.error(f"Error starting campaign {campaign_data.campaign_id}: {e}")

        logger.info("All campaigns have been started.")
        return True
    except Exception as e:
        logger.error(f"Error starting all campaigns: {e}")
        return False
@app.before_request
def create_tables():
    # The following line will remove this handler, making it
    # only run on the first request
    app.before_request_funcs[None].remove(create_tables)

    db.create_all()


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
    all_campaigns = CampaignModel.query.all()
    campaigns = [campaign.to_dict() for campaign in all_campaigns]
    return render_template("index.html", user=current_user, campaigns=campaigns)


@app.route("/create_campaign", methods=["GET", "POST"])
@login_required
def create_campaign():
    if request.method == "POST":
        video_link = request.form["youtube_url"]
        video_id = video_link.split("v=")[1]
        genre = request.form["genre"]
        comments_sheet = request.form["comments_sheet"]
        # Clean the comments sheet URL
        comments_sheet = comments_sheet.replace(" ", "")
        # Strip everything after the sheet id
        parts = comments_sheet.split("/")
        comments_sheet = "/".join(parts[:6])
        comments_sheet = comments_sheet.rstrip("/")
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
            campaign_data = CampaignModel(
                campaign_id=str(uuid.uuid4()),  # Generate a unique campaign ID
                video_title=title,
                video_link=video_link,
                video_id=video_id,
                genre=genre,
                comments_sheet_url=comments_sheet,
                wait_time=wait_time,
                status="Running",
                likes=likes,
                comments=comments,
                views=views,
            )
            db.session.add(campaign_data)
            save_db_changes()

            campaign = Campaign(campaign_data.to_dict(), rc, comments_sheet, wait_time)
            # Start the campaign in a new thread
            flash("Campaign created and running!", "success")
            campaign_thread = threading.Thread(target=campaign.run, args=(views,))
            campaign_thread.start()
            campaign_threads[campaign_data.campaign_id] = (campaign, campaign_thread)

            return redirect(url_for("index"))
        except Exception as e:
            flash(f"An error occurred: {str(e)}", "danger")
            return redirect(url_for("index"))
    flash("Please enter a YouTube video link and upload comments first.", "danger")
    return redirect(url_for("index"))


@app.route("/campaign_status/<campaign_id>", methods=["GET"])
@login_required
def campaign_status(campaign_id):
    campaign, _ = campaign_threads.get(campaign_id, (None, None))
    logger.info(f"Starting campaign status long polling for {campaign_id}")
    try:
        if campaign:
            data = {
                "views": campaign.ratio_calculator.views,
                "likes": campaign.ratio_calculator.likes,
                "comments": campaign.ratio_calculator.comments,
                "status": campaign.data["Status"],
                "desired_comments": (
                    np.floor(campaign.desired_comments)
                    if campaign.desired_comments
                    else 0
                ),
            }
            logger.info(f"Video ID: {campaign.data['Video ID']}," f"Data: {data}")
            logger.info(f"Data: {data}")
            return jsonify(data)
        else:
            return jsonify({"error": "Campaign not found"}), 404
    except Exception as e:
        logger.error(f"An error occurred: {str(e)}")
        return jsonify({"error": str(e)}), 500
    finally:
        logger.info(f"Ending campaign status long polling for {campaign_id}")


@app.route("/start_campaign/<campaign_id>", methods=["POST"])
@login_required
def start_campaign(campaign_id):
    try:
        logger.info(f"Starting campaign {campaign_id}")
        campaign_data = CampaignModel.query.get(campaign_id)
        if campaign_data and campaign_data.status == "Completed":
            # Stop the campaign if it is already running
            stop_campaign_thread(campaign_id)
            logger.info(f"Restarting campaign {campaign_id}")
            rc = YoutubeRatioCalc(API_KEY, campaign_data.video_id)
            rc.get_views_likes_cmnts()
            rc.get_video_title()
            campaign = Campaign(
                campaign_data.to_dict(),
                rc,
                campaign_data.comments_sheet_url,
                campaign_data.wait_time,
            )
            campaign.data["Status"] = "Running"
            campaign_thread = threading.Thread(
                target=campaign.run, args=(campaign.data["Views"],)
            )
            campaign_thread.start()
            campaign_threads[campaign_id] = (campaign, campaign_thread)
            campaign_data.status = "Running"
            save_db_changes()
        return redirect(url_for("index"))
    except Exception as e:
        logger.error(f"An error occurred: {str(e)}")
        return redirect(url_for("index"))


@app.route("/stop_campaign/<campaign_id>", methods=["POST"])
@login_required
def stop_campaign(campaign_id):
    logger.info(f"Stopping campaign {campaign_id}")
    campaign = CampaignModel.query.get(campaign_id)
    campaign.status = "Completed"
    save_db_changes()
    campaign, campaign_thread = campaign_threads.get(campaign_id, (None, None))
    # Stop the campaign
    if campaign:
        logger.info(f"Stopping campaign {campaign_id} thread")
        campaign.stop()
        # Stop the campaign asynchronously
        thread = threading.Thread(target=stop_campaign_thread, args=(campaign_id,))
        thread.start()
    # Remove the campaign from the campaign_threads dictionary
    campaign_threads.pop(campaign_id, None)
    return redirect(url_for("index"))


@app.route("/export_campaigns", methods=["GET"])
@login_required
def export():
    all_campaigns = CampaignModel.query.all()
    campaigns = [campaign.to_dict() for campaign in all_campaigns]
    campaigns_df = pd.DataFrame(campaigns)
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
            logger.info(f"Stopping campaign {campaign_id} thread")
            thread = threading.Thread(target=stop_campaign_thread, args=(campaign_id,))
            thread.start()
    # Clear the campaign_threads dictionary
    campaign_threads.clear()
    # Clear the campaigns in the session
    db.session.query(CampaignModel).update({CampaignModel.status: "Completed"})
    save_db_changes()
    logger.info("All campaigns stopped!")
    # Update the status of all campaigns in the session
    flash("All campaigns stopped!", "success")
    return redirect(url_for("index"))

@app.route("/start_all_campaigns", methods=["POST"])
@login_required
def start_all():
    start_all_campaigns(campaign_threads, db, CampaignModel)
    logger.info("All campaigns have been started!")
    flash("All campaigns have been started!", "success")
    return redirect(url_for("index"))

@app.route("/clear_all_campaigns", methods=["POST"])
@login_required
def stop_all_campaigns():
    stop_and_clear_all_campaigns(campaign_threads, db, CampaignModel)
    logger.info(
        "All campaigns have been stopped, cleared, and removed from the database!"
    )
    flash(
        "All campaigns have been stopped, cleared, and removed from the database!",
        "success",
    )
    return redirect(url_for("index"))


if __name__ == "__main__":
    app.run(debug=True)
