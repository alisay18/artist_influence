import json
import os
import threading
import uuid

import pandas as pd
from dotenv import load_dotenv
from flask import (Flask, flash, redirect, render_template, request, send_file,
                   send_from_directory, session, url_for)

from campaign import Campaign, YoutubeRatioCalc
from jingle_smm import JingleSMM

load_dotenv()
API_KEY = os.getenv("YOUTUBE_API_KEY")

app = Flask(__name__, template_folder="templates")
app.secret_key = (
    "your_secret_key"  # You should use a secure and random secret key for production
)

# Global dictionary to store campaign threads
campaign_threads = {}


campaigns = pd.DataFrame(
    columns=[
        "Video Link",
        "Video ID",
        "Channel ID",
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


@app.route("/", methods=["GET", "POST"])
def index():
    return render_template(
        "YTTableTest2.html", campaigns=json.loads(session.get("campaigns", "[]"))
    )


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
        video_link=session["video_link"],
        video_id=session["video_id"],
        likes=session["likes"],
        comments=comments,
        views=session["views"],
    )


@app.route("/create_campaign", methods=["GET", "POST"])
def create_campaign():
    if request.method == "POST":
        video_link = request.form["youtube_url"]
        video_id = video_link.split("v=")[1]
        channel_id = request.form["channel_id"]
        genre = request.form["genre"]
        comments_sheet = request.form["comments_sheet"]
        wait_time = int(request.form["wait_time"])
        rc = YoutubeRatioCalc(API_KEY, video_id, channel_id)
        likes, comments, views = rc.get_views_likes_cmnts()
        if not video_id:
            flash(
                "Please enter a YouTube video link and upload comments first.", "danger"
            )
            return redirect(url_for("index"))

        try:
            calculator = YoutubeRatioCalc(API_KEY, video_id, channel_id)
            campaign_data = {
                "Video Link": video_link,
                "Video ID": video_id,
                "Channel ID": channel_id,
                "Genre": genre,
                "Comments Sheet URL": comments_sheet,
                "Wait Time": wait_time,
                "Status": "Running",
                "Likes": likes,
                "Comments": comments,
                "Views": views,
                "Campaign ID": str(uuid.uuid4()),  # Generate a unique campaign ID
            }
            campaign = Campaign(campaign_data, calculator, comments_sheet, wait_time)
            # Convert session campaigns to DataFrame, append the new campaign, and save back to session
            campaigns_df = pd.DataFrame(json.loads(session.get("campaigns", "[]")))
            campaigns_df = pd.concat(
                [campaigns_df, pd.DataFrame([campaign_data])], ignore_index=True
            )
            session["campaigns"] = campaigns_df.to_json(orient="records")
            print(session["campaigns"])
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
    return render_template("create_campaign.html")


@app.route("/start_campaign/<campaign_id>", methods=["POST"])
def start_campaign(campaign_id):
    campaigns_df = pd.DataFrame(json.loads(session.get("campaigns", "[]")))
    campaign_data = campaigns_df.loc[campaigns_df['Campaign ID'] == campaign_id].to_dict(orient='records')[0]
    campaign_data["Status"] = "Running"
    campaigns_df.loc[campaigns_df['Campaign ID'] == campaign_id, "Status"] = "Running"
    session["campaigns"] = campaigns_df.to_json(orient="records")
    
    # Restart the campaign
    campaign, _ = campaign_threads.get(campaign_id, (None, None))
    if campaign:
        campaign.stop_flag.clear()
        campaign_thread = threading.Thread(target=campaign.run, args=(campaign.data["Views"],))
        campaign_thread.start()
        campaign_threads[campaign_id] = (campaign, campaign_thread)
    
    return redirect(url_for("index"))


@app.route("/stop_campaign/<campaign_id>", methods=["POST"])
def stop_campaign(campaign_id):
    campaigns_df = pd.DataFrame(json.loads(session.get("campaigns", "[]")))
    campaign_data = campaigns_df.loc[campaigns_df['Campaign ID'] == campaign_id].to_dict(orient='records')[0]
    campaign_data["Status"] = "Completed"
    campaigns_df.loc[campaigns_df['Campaign ID'] == campaign_id, "Status"] = "Completed"
    session["campaigns"] = campaigns_df.to_json(orient="records")
    
    # Stop the campaign
    campaign, campaign_thread = campaign_threads.get(campaign_id, (None, None))
    if campaign:
        campaign.stop()
        campaign_thread.join()
    
    return redirect(url_for("index"))


@app.route("/export")
def export():
    campaigns_df = pd.DataFrame(json.loads(session.get("campaigns", "[]")))
    campaigns_df.to_csv("campaigns_report.csv", index=False)
    return send_file("campaigns_report.csv", as_attachment=True)


@app.route("/stop", methods=["POST"])
def stop():
    for campaign_id, (campaign, campaign_thread) in campaign_threads.items():
        if campaign_thread.is_alive():  # Check if the thread is still running
            campaign.stop()  # Signal the campaign to stop
            campaign_thread.join()  # Wait for the thread to finish
    # Clear the campaign_threads dictionary
    campaign_threads.clear()
    # Update the status of all campaigns in the session
    campaigns_df = pd.DataFrame(json.loads(session.get("campaigns", "[]")))
    campaigns_df["Status"] = "Completed"
    session["campaigns"] = campaigns_df.to_json(orient="records")
    flash('All campaigns stopped!', 'success')
    return redirect(url_for("index"))


if __name__ == "__main__":
    app.run(debug=True)
