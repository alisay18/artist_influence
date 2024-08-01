# Copyright (c) 2024, Artist Influence Development Team
# All rights reserved.

import os
import sys
import threading
import time

import pandas as pd
from dotenv import load_dotenv
from flask import Flask, redirect, render_template, request, send_file, session, url_for
from jingle_smm import JingleSMM

from ratio_app.campaign import YoutubeRatioCalc

load_dotenv()
API_KEY = os.getenv("YOUTUBE_API_KEY")

app = Flask(__name__, template_folder="templates")
app.secret_key = (
    "your_secret_key"  # You should use a secure and random secret key for production
)
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
running = True


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


# Helper function to process video details
def get_video_details(video_id):
    print(API_KEY)
    rc = YoutubeRatioCalc(API_KEY, video_id=video_id)
    likes, comments, views = rc.get_views_likes_cmnts()
    ratio = rc.calculate_ratio(likes, comments)
    return likes, comments, views, ratio


@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        video_id = request.form["YTlink"]
        likes, _, views, ratio = get_video_details(video_id)
        session["video_id"] = video_id
        session["likes"] = likes
        session["views"] = views
        session["ratio"] = ratio
        return render_template(
            "YTTableTest2.html",
            video_id=video_id,
            likes=likes,
            views=views,
            ratio=ratio,
        )

    return render_template("YTTableTest2.html")


@app.route("/upload", methods=["POST"])
def upload_file():
    file = request.files["comments"]
    new_data = load_csv(file)
    # Convert the DataFrame to a string with rows separated by '\n'
    df_string = new_data.to_string(index=False)

    # Optional: Add newline characters between rows
    comments = "\n".join(df_string.split("\n"))
    session["comments"] = comments
    return render_template(
        "index2.html",
        video_id=session["video_id"],
        likes=session["likes"],
        comments=comments,
        views=session["views"],
        ratio=session["ratio"],
    )


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
    threading.Thread(
        target=process_campaign(session["comments"], session["video_id"])
    ).start()
    return render_template("index2.html")


if __name__ == "__main__":
    threading.Thread(target=process_campaign).start()
    app.run(debug=True)
