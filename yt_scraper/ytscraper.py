#TODO: 
# 1. Add error handling for s3 bucket creation
# 2. Add error handling for s3 upload
# 3. Ensure we aren't reprocessing old date (might be just fine tuning run frequency  / queries)
# 4. Remove YT API Key from source
# 5. Think thru logging

import os
import re
import boto3
import requests
import time

import googleapiclient.discovery
import googleapiclient.errors
from datetime import datetime


def main():
    scrape_yt()

if __name__ == "__main__":
    main()

def scrape_yt(api_keys="",
            max_pages = 5,
            max_results = 50,
            location="",
            location_radius="",
            query="official music video", disable_https=False):
    # Disable OAuthlib's HTTPS verification when running locally.
    # *DO NOT* leave this option enabled in production.
    if disable_https:
        os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"
    print(api_keys)

    # Use first key passed. 
    # If list, set rest into api_keys list
    if type(api_keys) is list:
        api_key = api_keys[0]
        api_keys = api_keys[1:]
    elif type(api_keys) is str:
        api_key = api_keys
        api_keys = []
    

    youtube = googleapiclient.discovery.build(
        "youtube", "v3", developerKey=api_key)

    # Get a list of channels
    items_found = 0
    pages = 0
    next_page_token = ""
    match_list = {}
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
                    pageToken=next_page_token
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
                    pageToken=next_page_token
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
                        "youtube", "v3", developerKey=api_key)
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
        for item in search_response["items"]:
            try:
                request = youtube.channels().list(
                    part="snippet",
                    id=item["snippet"]["channelId"]
                )
            except googleapiclient.errors.HttpError as e:
                if e.resp.status == 403:
                    # Handle the 403 error here
                    # Rotate key and decrement page count to repeat
                    print("Error: YouTube API request forbidden.")
                    if api_keys:
                        api_key = api_keys.pop(0)
                        youtube = googleapiclient.discovery.build(
                            "youtube", "v3", developerKey=api_key)
                    else:
                        print("No more API keys to try")
                        return e
                else:
                    return e
            channel_response = request.execute()

            description = channel_response["items"][0]["snippet"]["description"].replace("\n", " ")
            matches = re.findall(r"[\w\-][\w\-\.]+@[\w\-][\w\-\.]+[a-zA-Z]{1,4}", description)
            if matches:
                channel_title = channel_response["items"][0]["snippet"]["title"]
                if channel_title not in match_list:
                    match_list[channel_title] = []
                    match_list[channel_title].append(matches)
                items_found += 1

    match_list = convert_matches_to_csv(match_list)

    print("!! PAGES SEARCHED: ", pages)
    print("!! ITEMS FOUND: ", items_found)
    print("!! FOUND MATCHES: ", match_list)

    # Upload email matches to s3 bucket in file with name var with timestamp appended
    # upload_to_s3(str(match_list), "ytscraper", query)
    # Upload as csv to google sheets
    upload_to_mixmax(match_list)
    

def convert_matches_to_csv(match_list):
    # Convert match_list to csv format
    conv_emails = []
    csv = ""
    for channel in match_list:
        for emails in match_list[channel]:
            for email in emails:
                if email not in conv_emails:
                    csv += channel + "," + email + "\n"
                    conv_emails.append(email)
    return csv

def make_s3_key_safe(key):
    """Make a string safe for use as an S3 object key"""

    # Remove invalid characters that would prevent object from being saved
    key = re.sub(r'[^\w\s-]', '', key)

    # Replace spaces with hyphens
    key = re.sub(r'[\s]+', '-', key)

    return key

def add_timestamp_and_truncate(key):
    # Generate timestamp 
    timestamp = datetime.now().strftime("%Y%m%d%H%M")

    # Check if key is more than 1024 bytes (S3 limit), less the timestamp
    # truncate it to make room if so
    if len(key.encode('utf-8')) > 1024 - len(timestamp.encode('utf-8')):
        key = key[:1024 - len(timestamp.encode('utf-8'))]

    # Append timestamp to object name
    key = key + timestamp
    return key

def upload_to_s3(data, bucket, object_name=None):
    s3 = boto3.client('s3')

    object_name = add_timestamp_and_truncate(make_s3_key_safe(object_name))

    # create bucket if it doesn't exist, with error handling
    s3.create_bucket(Bucket=bucket)
    s3.put_object(Bucket=bucket, Key=object_name, Body=data)


def upload_to_mixmax(data) -> None:
    """_summary_

    Args:
        data (_type_): _description_
        sheet_id (_type_): _description_
    """
    url = "https://api.mixmax.com/v1/sequences/65d4db2286af8c7e2146eaa1/recipients/"

    # Parse the data into the correct format
    recipients = []
    # split the data into lines
    lines = data.split("\n")
    # split each line into a list of values
    for line in lines:
        channel_info = line.split(",")
        # if there are less than 2 values, skip adding to the list
        if (len(channel_info) < 2):
            continue
        recipients.append({
            "email": channel_info[1],
            "variables": {  
                "name": channel_info[0],
                "email": channel_info[1]
            },
            "scheduledAt": round(2*time.time() * 1000)
        })
    print(time.time() + 10000)
    payload = {
        "recipients": recipients,
        "scheduledAt":  round(2*time.time() * 1000),
        "enrich": True,
        "allowMissingVariables": False
    }
    headers = {
        "accept": "application/json",
        "content-type": "application/json",
        "X-API-Token": "MIX_MAX_TOKEN"
    }

    print(payload)
    #response = requests.post(url, json=payload, headers=headers)

    # print(response.text)