import os
import threading
import time
from datetime import datetime

import pandas as pd
import requests
import schedule
from dotenv import load_dotenv
from flask import Flask, redirect, render_template, request, send_file, url_for
from googleapiclient.discovery import build

app = Flask(__name__, template_folder="any")
campaigns = pd.DataFrame(
    columns=[
        "URL",
        "Genre",
        "Views",
        "Comments",
        "Likes",
        "Status",
        "Views_Generated",
        "Likes_Generated",
        "Comments_Generated",
    ]
)
api_url = "https://jingle-smm-api.com/drip"  # Mock URL for the Jingle SMM API
running = True

load_dotenv()


def load_csv(file_path):
    return pd.read_csv(file_path)


def get_video_details(video_id, api_key):
    # Build a service object for interacting with the API
    youtube = build("youtube", "v3", developerKey=api_key)

    # Fetch video details
    request = youtube.videos().list(part="statistics", id=video_id)
    response = request.execute()

    # Extract details from the response
    if response["items"]:
        statistics = response["items"][0]["statistics"]
        likes = int(statistics.get("likeCount", "0"))
        comments = int(statistics.get("commentCount", "0"))
        views = int(statistics.get("viewCount", "0"))
        return likes, comments, views
    else:
        return None, None


def drip_engagement(video_url, likes_needed, comments_needed, comments):
    for comment in comments:
        response = requests.post(
            api_url, data={"video_url": video_url, "likes": 1, "comment": comment}
        )
        if response.status_code != 200:
            print(f"Failed to post engagement for {video_url}")
        time.sleep(1)


def calculate_ratio(likes, comments):
    # Calculate the like-to-comment ratio
    if comments == 0:
        return float("inf")  # Avoid division by zero
    return likes / comments


# Replace YOUR_API_KEY with your actual YouTube Data API key
API_KEY = os.getenv("YOUTUBE_LIKES_COMMENTS_KEY")
VIDEO_ID = "f4eDOMk4ef0"  # Replace with the YouTube video ID you want to analyze

likes, comments, views = get_video_details(VIDEO_ID, API_KEY)
if likes is not None and comments is not None:
    ratio = calculate_ratio(likes, comments)
    print(
        f"Likes: {likes}, Comments: {comments}, Views: {views}, Like-to-Comment Ratio: {ratio}"
    )
else:
    print("Failed to retrieve video details")


def process_campaign():
    global running
    while running:
        for index, row in campaigns.iterrows():
            if row["Status"] == "Active":
                stats = get_video_details(row["URL"])
                views = stats["views"]
                expected_likes = views * 0.1  # Example ratio
                expected_comments = views * 0.02  # Example ratio
                likes_needed = max(0, int(expected_likes - row["Likes"]))
                comments_needed = max(0, int(expected_comments - row["Comments"]))
                comments = row["Comments"].split(";")
                drip_engagement(
                    row["URL"],
                    likes_needed,
                    comments_needed,
                    comments[:comments_needed],
                )
                campaigns.at[index, "Likes_Generated"] += likes_needed
                campaigns.at[index, "Comments_Generated"] += comments_needed
        time.sleep(3600)


@app.route("/")
def index():
    return render_template(
        "templates/index.html",
        tables=[campaigns.to_html(classes="data", header="true")],
    )


@app.route("/upload", methods=["POST"])
def upload_file():
    file = request.files["file"]
    global campaigns
    new_data = load_csv(file)
    campaigns = pd.concat([campaigns, new_data], ignore_index=True)
    return redirect(url_for("index"))


@app.route("/start_campaign/<int:campaign_id>")
def start_campaign(campaign_id):
    campaigns.at[campaign_id, "Status"] = "Active"
    return redirect(url_for("index"))


@app.route("/stop_campaign/<int:campaign_id>")
def stop_campaign(campaign_id):
    campaigns.at[campaign_id, "Status"] = "Completed"
    return redirect(url_for("index"))


@app.route("/export")
def export():
    campaigns.to_csv("campaigns_report.csv", index=False)
    return send_file("campaigns_report.csv", as_attachment=True)


@app.route("/stop")
def stop():
    global running
    running = False
    return redirect(url_for("index"))


@app.route("/start")
def start():
    global running
    running = True
    threading.Thread(target=process_campaign).start()
    return redirect(url_for("index"))


if __name__ == "__main__":
    threading.Thread(target=process_campaign).start()
    app.run(debug=True)
