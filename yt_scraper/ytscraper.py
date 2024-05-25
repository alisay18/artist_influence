# TODO:
# 1. Add error handling for s3 bucket creation
# 2. Add error handling for s3 upload
# 3. Ensure we aren't reprocessing old date (might be just fine tuning run frequency  / queries)
# 4. Remove YT API Key from source
# 5. Think thru logging

import os
import re
import csv
import boto3
import requests
import time

import googleapiclient.discovery
import googleapiclient.errors
from datetime import datetime, timedelta

import os
from dotenv import load_dotenv

import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication

load_dotenv()


def scrape_yt(
    city,
    location,
    api_keys=os.getenv("YOUTUBE_API_KEY"),
    max_pages=25,
    max_results=500,
    location_radius="500km",
    query="(Official Music Video)",
    disable_https=False,
):
    print("Using location: ", location)
    print("Using radius: ", location_radius)

    # Initialize a dictionary to track scraped emails for each city
    scraped_emails = {}

    # Check if the location key exists in the dictionary, if not, create it
    if location not in scraped_emails:
        scraped_emails[location] = set()

    # Get current time and time 24 hours ago
    now = datetime.utcnow()
    published_after = (now - timedelta(days=7)).isoformat("T") + "Z"
    print(f"Filtering videos published after: {published_after}")

    search_response = {}

    # Disable OAuthlib's HTTPS verification when running locally.
    # *DO NOT* leave this option enabled in production.
    if disable_https:
        os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"
    print(api_keys, "my key")

    # Use first key passed.
    # If list, set rest into api_keys list
    if type(api_keys) is list:
        api_key = api_keys[0]
        api_keys = api_keys[1:]
    elif type(api_keys) is str:
        api_key = api_keys
        api_keys = []

    youtube = googleapiclient.discovery.build("youtube", "v3", developerKey=api_key)

    # Get a list of channels
    items_found = 0
    pages = 0
    next_page_token = ""
    match_list = ""
    while pages < max_pages:
        pages += 1
        try:
            if location != "" and location_radius != "":
                request = youtube.search().list(
                    part="snippet",
                    channelType="any",
                    maxResults=max_results,
                    order="date",
                    q=query,
                    safeSearch="none",
                    type="video",
                    location=location,
                    locationRadius=location_radius,
                    pageToken=next_page_token,
                    videoCategoryId="10",
                )
            else:
                request = youtube.search().list(
                    part="snippet",
                    channelType="any",
                    maxResults=max_results,
                    order="date",
                    q=query,
                    safeSearch="none",
                    type="video",
                    pageToken=next_page_token,
                    publishedAfter=published_after,
                    relevanceLanguage="en",
                    videoCategoryId="10",
                )
            search_response = request.execute()
        except googleapiclient.errors.HttpError as e:
            print("Error: " + str(e))
            if e.resp.status == 403:
                # Handle the 403 error here
                # Rotate key and decrement page count to repeat
                print("Error: YouTube API request forbidden.")
                if api_keys:
                    api_key = api_keys.pop(0)
                    print("Rotating key to: " + api_key)
                    youtube = googleapiclient.discovery.build(
                        "youtube", "v3", developerKey=api_key
                    )
                    pages = 0
                else:
                    print("No more API keys to try")
                    return e
            else:
                return e
        if "nextPageToken" in search_response:
            next_page_token = search_response["nextPageToken"]
        else:
            print("!! NO MORE PAGES")
            break

        # Loop through channels and search description for an email
        print("!! ITEMS FOUND: ", len(search_response["items"]))
        for item in search_response["items"]:
            try:
                request = youtube.channels().list(
                    part="snippet", id=item["snippet"]["channelId"]
                )
                channel_response = request.execute()
            except googleapiclient.errors.HttpError as e:
                if e.resp.status == 403:
                    # Handle the 403 error here
                    # Rotate key and decrement page count to repeat
                    print("Error: YouTube API request forbidden.")
                    if api_keys:
                        api_key = api_keys.pop(0)
                        youtube = googleapiclient.discovery.build(
                            "youtube", "v3", developerKey=api_key
                        )
                    else:
                        print("No more API keys to try")
                        return e
                else:
                    return e
            channel_response = request.execute()

            description = channel_response["items"][0]["snippet"][
                "description"
            ].replace("\n", " ")
            matches = re.findall(
                r"[\w\-][\w\-\.]+@[\w\-][\w\-\.]+[a-zA-Z]{1,4}", description
            )
            channel_title = channel_response["items"][0]["snippet"]["title"]
            # strip out new lines and commas
            channel_title = channel_title.replace("\n", " ").replace(",", " ")

            # channel description
            channel_description = channel_response["items"][0]["snippet"]["description"]
            # strip out new lines and commas
            channel_description = channel_description.replace("\n", " ").replace(",", " ")
            
            # strip multiple spaces
            channel_description = re.sub(' +', ' ', channel_description)

            # strip tabs
            channel_description = channel_description.replace("\t", " ")

            # strip new paragraphs
            channel_description = channel_description.replace("\r", " ")

            # remove any commas
            channel_description = channel_description.replace(",", " ")


            # get the video description
            video_description = channel_response["items"][0]["snippet"]["description"]

            # strip out new lines and commas
            video_description = video_description.replace("\n", " ").replace(",", " ")

            # strip multiple spaces
            video_description = re.sub(' +', ' ', video_description)

            # remove ascii characters
            video_description =video_description.encode('ascii', 'ignore').decode('ascii')
        

            # strip tabs
            video_description = video_description.replace("\t", " ")

            # strip new paragraphs
            video_description = video_description.replace("\r", " ")

            video_title = item['snippet']['title']
            # strip out new lines and commas
            video_title = video_title.replace("\n", " ").replace(",", " ")
            if matches:
                match_list += f"{channel_title},{channel_description},{video_title},{item['id']['videoId']},{video_description},{','.join(matches)}\n"
                items_found += 1
            else:
                match_list += f"{channel_title},{channel_description},{video_title},{item['id']['videoId']},{video_description},no emails\n"
                items_found += 1

    print(match_list)
    write_emails_to_csv(match_list, filename=f"{city}.csv")

    print("!! PAGES SEARCHED: ", pages)
    print("!! ITEMS FOUND: ", items_found)
    print("!! FOUND MATCHES: ", match_list)

    # Upload email matches to s3 bucket in file with name var with timestamp appended
    # upload_to_s3(str(match_list), "ytscraper", query)
    # Upload as csv to google sheets
    # upload_to_mixmax(match_list)


# Define the new CSV writing function
def write_emails_to_csv(match_list, filename="emails.csv"):
    with open(filename, "w", newline="\n") as file:
        writer = csv.writer(file)
        writer.writerow(
            [
                "Channel",
                "Channel Description",
                "Video Title",
                "Video ID",
                "Video Description",
                "Email1",
                "Email2",
                "Email3",
            ]
        )  # header row
        print(match_list)
        match_list = list(filter(bool, match_list.splitlines()))
        for email in match_list:
            writer.writerow(email.split(","))
    print(f"CSV file '{filename}' has been created and saved.")


def get_cities():
    # return {"Berlin": "52.5200, 13.4050",   "New York": "40.7128, -74.0060", "London": "51.5074, -0.1278", "Los Angeles": "34.0549, 118.2426", "Chicago": "41.8781, -87.6298", "Atlanta":"33.7488, 84.3877", "Miami": "25.7617, 80.1918", "Nashville": "25.7617, 80.1918", "Austin": "30.2672, -97.7431", "Houston": "29.7604, -95.3698", "London": "51.5072, -0.1276", "Seoul": "37.5519, 126.9918", "Seattle": "47.6061, 122.3328", "Amsterdam": "52.3676, 4.9041", "Detroit": "42.3314, -83.0458", "Toronto": "43.6532, -79.3832", "Montreal": "45.5019, -73.5674", "Vancouver": "49.2827, -123.1207", "San Francisco": "37.7749, -122.4194", "Denver": "39.7392, -104.9903", "Philadelphia": "39.9526, -75.1652", "Washington D.C.": "38.9072, -77.0369", "Jersey City": "40.7178, -74.0431", "Boston": "42.3601, -71.0589", "Baltimore": "39.2904, -76.6122", "Salt Lake City": "40.7608, -111.8910"}
    return {"New York": "40.7128, -74.0060"}


def send_email_with_attachment(receiver_email, attachment_path, attachment_filename):
    # Email configuration
    sender_email = "alisa@artistinfluence.com"
    sender_password = "mfrp sejz tpkw qjee"
    smtp_server = "smtp.gmail.com"
    smtp_port = 587  # Change this if necessary

    # Create a multipart message
    message = MIMEMultipart()
    message["From"] = sender_email
    message["To"] = receiver_email
    message["Subject"] = "NEW CSV File Attachment"

    # Add body to email (optional)
    body = "Please find attached the CSV file."
    message.attach(MIMEText(body, "plain"))

    # Open the file to be sent
    with open(attachment_path, "rb") as attachment:
        # Add file as application/octet-stream
        # Email client can usually download this automatically as attachment
        part = MIMEApplication(attachment.read(), Name=attachment_filename)
        # Add header as key/value pair to attachment part
        part["Content-Disposition"] = f'attachment; filename="{attachment_filename}"'
        # Attach part into message container
        message.attach(part)

    # Start SMTP server session
    server = smtplib.SMTP(smtp_server, smtp_port)
    server.starttls()  # Secure the connection
    # Login to SMTP server
    server.login(sender_email, sender_password)

    # Send email
    server.send_message(message)

    # Close SMTP server session
    server.quit()


def main():
    # Step 1: Copy code to scrape multiple cities.
    list_of_cities = get_cities()
    for city, coordinate in list_of_cities.items():
        scrape_yt(city, coordinate)

        # Send email with the generated CSV file
        csv_filename = f"{city}.csv"
        attachment_path = f"{city}.csv"
        send_email_with_attachment("jared@artistinfluence.com", attachment_path, csv_filename)


if __name__ == "__main__":
    main()
