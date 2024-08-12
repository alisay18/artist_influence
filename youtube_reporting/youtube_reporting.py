# Copyright (c) 2024, Artist Influence Development Team
# All rights reserved.

import datetime
import os
import smtplib
from dotenv import load_dotenv
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import pandas as pd
from google.auth.transport.requests import Request
from google.oauth2 import service_account
from googleapiclient.discovery import build

# Load environment variables from .env file
load_dotenv()
api_key = os.getenv("OPERATIONS_YOUTUBE_API_KEY")
print(api_key, 'APIKEY')

# TODO: I've also added a get_video_title function to get the title of the video, please use the youtube ratio calculator class to get the video title
def get_video_details(api_key, video_id, date):
    """_summary_

    Returns:
        _type_: _description_
    """
    youtube = build("youtube", "v3", developerKey=api_key)
    request = youtube.videos().list(part="statistics", id=video_id)
    response = request.execute()

    if response["items"]:
        statistics = response["items"][0]["statistics"]
        likes = int(statistics.get("likeCount", "0"))
        comments = int(statistics.get("commentCount", "0"))
        views = int(statistics.get("viewCount", "0"))
        subscribers = int(statistics.get("subscriberCount", "0"))
        # Set the video details

        video_details = {
            "likes": likes,
            "comments": comments,
            "views": views,
            "subcribers": subscribers,
        }
        # Get genre
        print(response, video_details)

        return likes, comments, views, subscribers
    else:
        return None, None, None


def load_data(file_path: str, dtype: dict = None):
    try:
        df = pd.read_csv(
            file_path,
            # Set first column as rownames in data frame
            index_col=0,
            # Set the data types of the columns
            dtype=dtype,
        )
    except Exception as e:
        print(f"Failed to load data from {file_path}")
        raise e
    # print(df.head())
    return df


def get_stats_seven_days_ago():
    try:
        # Get the current time and seven days ago
        now = datetime.datetime.now()
        seven_days_ago = now - datetime.timedelta(days=7)

        # Format dates for the API request
        end_date = now.strftime("%Y-%m-%d")
        start_date = seven_days_ago.strftime("%Y-%m-%d")

        # TODO: Your filepath on line 76 will not necessarily work on other people's computer (they dont have their client secret stored in the same place)
        # TODO: Please fix this by changing it to an environment variable or a relative path
        # Load credentials from the service account file
        credentials_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
        credentials = service_account.Credentials.from_service_account_file(
            credentials_path,
            scopes=["https://www.googleapis.com/auth/yt-analytics.readonly"],
        )
        youtube = build("youtubeAnalytics", "v2", developer=api_key)
        # Make the Analytics API request
        request = youtube.reports().query(
            ids=f"channel=={channel_id}",
            startDate=start_date,
            endDate=end_date,
            metrics=("views, likes, comments, subcribers"),
            dimensions="video",
            filters=f"video=={video_id}",
            sort="-views",
        )
        response = request.execute()

        # Parse the response
        if response.get("rows"):
            row = response["rows"][0]
            view_count = row[1]
            likes = row[2]
            comments = row[3]
            subscribers = row[4]
            return {
                "views": int(view_count),
                "likes": int(likes),
                "comments": int(comments),
                "subscribers": int(subscribers),
            }
        else:
            print("No data found for the specified video and time range.")
            return None

    except Exception as e:
        print(f"An error occurred: {str(e)}")
        return None


def get_video_title(api_key, video_id):

    youtube = build("youtube", "v3", developerKey=api_key)
    request = youtube.videos().list(part="snippet", id=video_id)
    response = request.execute()

    if response["items"]:
        title = response["items"][0]["snippet"]["title"]
        return title
    else:
        return None




# Send Email
# TODO: msg needs to be added to the email body
def send_email(name, receiver_email, msg):
    # Email Configuration
    smtp_server = "smtp.gmail.com"
    smtp_port = 587
    sender_email = "operations.ai@gmail.com"
    sender_password = "tzdx cent fonv pkaw"

    # Create a multipart message
    message = MIMEMultipart()
    message["From"] = sender_email
    message["To"] = receiver_email
    message["Subject"] = "YouTube Reporting Update"

    # Add body to email (optional)
    body = f"""
    Hey {name},I trust this email finds you in good spirits! Below, you'll find the latest update on our YouTube campaign for this week:\n 
    
    {msg}

    All audience data is available on YouTube Studio. If you have any questions, feel free to reach out!
    """
    message.attach(MIMEText(body, "plain"))

    # Start SMTP server session
    server = smtplib.SMTP(smtp_server, smtp_port)
    server.starttls()  # Secure the connection
    # Login to SMTP server
    server.login(sender_email, sender_password)

    # Send email
    server.send_message(message)

    # Close SMTP server session
    server.quit()


user_data = load_data(
    file_path="https://docs.google.com/spreadsheets/d/e/2PACX-1vSE58fcG7zdT4C73RQfUnq76R48AwyvsjkfSEOUhQTmHMthQqc-iklMyPLDMrL5mrIqZBwXoIBVFKkW/pub?gid=799904628&single=true&output=csv"
)

for index, user in user_data.iterrows():
    # Parse user input
    print(user, "user")
    msg = ""

    for i in range(4):
        video_id = user[f"Video ID {i+1}"]
        print(video_id)
        # TODO: Get the title of the video
        title = get_video_title(api_key, video_id)

        # Get current video details
        likes, comments, views, subscribers = get_video_details(api_key, video_id)

        # Calculate the date 7 days ago
        seven_days_ago = (datetime.datetime.now() - datetime.timedelta(days=7)).strftime(
            "%Y-%m-%d"
        )

        # Get video details from seven days agp
        likes_7d, comments_7d, views_7d, subscribers_7d = get_video_details(
            api_key, video_id, date=seven_days_ago
        )

        msg += (
            f"Video:{title}n"
            f"Current Stats - views: {views}, likes: {likes}, comments: {comments}, subscribers: {subscribers}\n"
            f"Past 7 days - Views: {views_7d}, Likes: {likes_7d}, Comments: {comments_7d}, Subscribers: {subscribers_7d}\n\n"
        )

    name = user["First Name"]
    email = user["Email"]
    send_email(name, email, msg, subscribers)


# TODO: To test the code, you can run the youtube_reporting.py file in the terminal and have an if __name__ == "__main__": block to run the code
# TODO: I've added an example below with github copilot the code may not necessarily be correct, you can get copilot for free with your academic account.
if __name__ == "__main__":
    user_data = load_data(
        file_path="https://docs.google.com/spreadsheets/d/e/2PACX-1vSE58fcG7zdT4C73RQfUnq76R48AwyvsjkfSEOUhQTmHMthQqc-iklMyPLDMrL5mrIqZBwXoIBVFKkW/pub?gid=799904628&single=true&output=csv"
    )

    for index, user in user_data.iterrows():
        # Parse user input
        print(user, "user")
        video_id = user["Video ID 1"]
        print(video_id)
        likes, comments, views, subscribers = get_video_details(api_key, video_id)
        name = user["First Name"]
        email = user["Email"]
        send_email(name, email, likes, comments, views, subscribers)
