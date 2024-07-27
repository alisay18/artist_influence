import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import pyotp
import google.auth
import pandas as pd
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from google.ads.googleads.client import GoogleAdsClient
from google.ads.googleads.errors import GoogleAdsException
import datetime

api_key = os.getenv("operations_youtube_api_key")


def get_video_details(api_key, video_id):
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

        video_details = {"likes": likes, "comments": comments, "views": views}
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
    print(df.head())
    return df


# Send Email
def send_email(name, receiver_email, views, likes, comments, subscribers):
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
    body = f"Hey {name},I trust this email finds you in good spirits! Below, you'll find the latest update on our YouTube campaign for this week:\n Title\nCurrent Views:{views}\nCurrent Likes:{likes}\nCurrent Comments:{comments}\nSubscribers Gained:{subscribers}\nPast 7 days:\nViews:\nComments:\nLikes:\nSubscribers:\nAll audience data is available on YouTube Studio. If you have any questions, feel free to reach out!"
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


user_data = load_data(file_path="example")

for user in user_data:
    # Parse user input
    video_id = user["Video ID"]
    likes, comments, views, subscribers = get_video_details(api_key, video_id)
    name = user["First Name"]
    email = user["Email"]
    send_email(name, email, likes, comments, views, subscribers)
