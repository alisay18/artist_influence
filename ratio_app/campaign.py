# Copyright (c) 2024, Artist Influence Development Team
# All rights reserved.

import logging as log
import os
import threading
import time

import numpy as np
import pandas as pd
from dotenv import load_dotenv
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

from jingle_smm import JingleSMM

# Load environment variables
load_dotenv()

# Set up logging
logger = log.getLogger(__name__)
logger.setLevel(log.INFO)
handler = log.StreamHandler()
handler.setFormatter(log.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
logger.addHandler(handler)

# Set up Google Sheets API
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]
SERVICE_ACCOUNT_FILE = (
    f"{os.path.dirname(__file__)}/rich-phenomenon-428302-q5-dba5f2f381c1.json"
)

creds = Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=SCOPES)

sheet_service = build("sheets", "v4", credentials=creds)


def load_data(file_path: str, dtype: dict = None):
    try:
        df = pd.read_csv(
            file_path,
            index_col=0,
            dtype=dtype,
        )
    except Exception as e:
        logger.error(f"Failed to load data from {file_path}: {e}")
        raise e
    logger.info(f"Loaded data from {file_path}")
    return df


class YoutubeRatioCalc:
    def __init__(
        self,
        api_key,
        video_id,
        music_gsheet="https://docs.google.com/spreadsheets/d/1k9A8viP4gFGjEwexNeLN6tmZyZ6YJIS_Ax6PxHjJvy8",
    ):
        self.api_key = api_key
        self.video_id = video_id
        self.video_details = None
        self.music_gsheet = music_gsheet
        self.likes, self.comments, self.views = self.get_views_likes_cmnts()

    def get_video_title(self):
        youtube = build("youtube", "v3", developerKey=self.api_key)
        request = youtube.videos().list(part="snippet", id=self.video_id)
        response = request.execute()

        if response["items"]:
            title = response["items"][0]["snippet"]["title"]
            return title
        else:
            return None

    def get_views_likes_cmnts(self):
        """Get the views, likes, and comments for a video.

        Returns:
            likes (int): The number of likes for the video.
            comments (int): The number of comments for the video.
            views (int): The number of views for the video.
        """
        try:
            youtube = build("youtube", "v3", developerKey=self.api_key)
            request = youtube.videos().list(part="statistics", id=self.video_id)
            response = request.execute()

            if response["items"]:
                statistics = response["items"][0]["statistics"]
                likes = int(statistics.get("likeCount", "0"))
                comments = int(statistics.get("commentCount", "0"))
                views = int(statistics.get("viewCount", "0"))

                self.video_details = {
                    "likes": likes,
                    "comments": comments,
                    "views": views,
                }
                self.likes, self.comments, self.views = likes, comments, views
                logger.info(f"Video details: {self.video_details}")
                return likes, comments, views
            else:
                logger.warning(f"No video details found for video ID: {self.video_id}")
                return None, None, None
        except Exception as e:
            logger.error(f"Error retrieving video details: {e}")
            return None, None, None

    def calculate_ratio(self, metric, views_arr, df):
        """Calculate the ratio of a metric to views.

        Args:
            metric (str): The metric to calculate the ratio for can be likes or comments.
            views_arr (list): The array of views.
            df (pd.DataFrame): The dataframe containing the data.

        Returns:
            np.poly1d: The polynomial function representing the ratio.
        """
        try:
            ratio_eq = np.polyfit(
                np.log(np.array(views_arr)), np.log(np.array(df[metric])), 1
            )
            ratio_error = 1 - np.sum(
                (np.polyval(ratio_eq, np.log(views_arr)) - np.log(df[metric])) ** 2
            ) / np.sum((np.log(df[metric]) - np.mean(np.log(df[metric]))) ** 2)

            if ratio_error < 0.80:
                ratio_eq = np.polyfit(np.log(views_arr), np.log(df[metric]), 3)

            return np.poly1d(ratio_eq)
        except Exception as e:
            logger.error(f"Error calculating ratio: {e}")
            raise e

    def desired_views_likes(self, genre, desired_views=None):
        df = load_data(
            self.music_gsheet + "/export?gid=1801952771&format=csv",
            {
                "#views": "int",
                "#likes": "int",
                "#comments": "int",
                "views": "int",
                "likes": "int",
                "comments": "int",
                "genre": "str",
                "like:view": "float",
                "comment:view": "float",
            },
        )
        genre_splice = df[df["genre"] == genre]
        comments_to_views_ratio = self.calculate_ratio(
            "#comments", genre_splice["#views"], genre_splice
        )
        likes_to_views_ratio = self.calculate_ratio(
            "#likes", genre_splice["#views"], genre_splice
        )
        views = self.video_details["views"] + desired_views
        desired_comments = np.e ** (comments_to_views_ratio(np.log(views)))
        desired_likes = np.e ** (likes_to_views_ratio(np.log(views)))
        return desired_comments, desired_likes


class Campaign:
    def __init__(self, data, ratio_calculator, comment_sheet, wait_time=36):
        self.data = data
        self.api = JingleSMM()
        self.damper = 0.05
        self.video_id = data["Video ID"]
        self.genre = data["Genre"]
        self.comments_sheet = comment_sheet
        self.comments_sheet_id = comment_sheet.split("/")[-1]
        self.num_used_comments = 0
        self.ratio_calculator: YoutubeRatioCalc = ratio_calculator
        self.wait_time = wait_time
        self.stop_flag = threading.Event()  # Add a stop flag

    def get_comments(self):
        if self.comments_sheet:
            comments = load_data(
                self.comments_sheet + "/export?format=csv",
                {"Comments": "str", "Used": "str"},
            )
            # if the used column is not present, add it
            self.num_used_comments = comments[comments["Used"] == "Used"].shape[0]
            # Remove comments that have already been used
            comments = comments[comments["Used"] != "Used"]
            logger.info(f"Loaded {comments.shape[0]} comments from the Google Sheet.")
            return comments
        else:
            return None

    def mark_comments_as_used(self, spreadsheet_id, comments):
        """
        Update the Google Sheet to mark the comments as used.

        Args:
            spreadsheet_id (str): The ID of the Google Sheet.
            comments (pd.DataFrame): The DataFrame containing the comments that were used.
        """
        try:
            # Assuming the comments are in the first column (A)
            used_comment_indices = len(comments.index.tolist()) + self.num_used_comments
            range_ = f"Sheet1!B2:B{used_comment_indices + 1}"
            # Prepare the data to be updated (e.g., mark with 'Used')
            update_values = [["Used"] for _ in range(used_comment_indices)]
            body = {"values": update_values}
            result = (
                sheet_service.spreadsheets()
                .values()
                .update(
                    spreadsheetId=spreadsheet_id,
                    range=range_,
                    valueInputOption="RAW",
                    body=body,
                )
                .execute()
            )

            logger.info(
                f"Updated {result.get('updatedCells')} cells in the Google Sheet."
            )

        except Exception as e:
            logger.error(f"Error updating the Google Sheet: {e}")

    def _generate_multiples_of_5(self, low, high):
        return [i for i in range(low, high + 1) if i % 5 == 0]

    def order_comments(
        self, comments, last_views, min_views, comments_db, used_comments, total_time=0
    ):
        if (
            self.ratio_calculator.views - last_views >= min_views
            and self.ratio_calculator.comments < self.desired_comments
        ):
            max_desired_comments = np.max(
                [
                    np.floor(
                        np.abs(
                            (1 - self.ratio_calculator.comments / self.desired_comments)
                            * (self.ratio_calculator.views - last_views)
                            * self.damper
                        )
                    ),
                    5,
                ]
            )
            max_comments = self._generate_multiples_of_5(5, int(max_desired_comments))
            # Use the video delta to determine how many comments to order
            diff = np.random.choice(max_comments)
            comments = comments_db.head(n=int(diff) if diff > 5 else 5)
            # Split comments into chunks of 5
            comment_chunks = [
                "\r\n".join(comments.index[i : i + 5])
                for i in range(0, len(comments), 5)
            ]
            logger.info(
                f"Ordering total of {comments.shape[0]} comments for {self.video_id}"
            )
            # Drip comments over the interval
            interval_seconds = np.random.randint(
                10800, 18000
            )  # Adjust this interval as needed
            for comment_chunk in comment_chunks:
                # if comment_chunk is less than 5, skip
                if len(comment_chunk.splitlines()) < 5:
                    # remove the comments from comments
                    comments = comments.drop(
                        comments.index[: len(comment_chunk.splitlines())]
                    )
                    continue
                if self.stop_flag.is_set():
                    break
                logger.info(
                    f"Video ID: {self.video_id} Ordering {len(comment_chunk.splitlines())} comments"
                )
                response = self.api.order(
                    {
                        "service": 440,
                        "link": f"https://www.youtube.com/watch?v={self.video_id}",
                        "comments": comment_chunk,
                    }
                )
                logger.info(f"Video ID: {self.video_id} Ordered comments: {response}")
                # Sleep between sending batches of comments to simulate "drip" effect
                time.sleep(interval_seconds)
                total_time += interval_seconds
            # Add the used comments to the used comments database
            used_comments = pd.concat([used_comments, comments])
            # Drop the used comments from the comments database
            comments_db.drop(comments.index, inplace=True)
            logger.info(f"Ordered comments: {response}")
            # Update the Google Sheet
            self.mark_comments_as_used(self.comments_sheet_id, used_comments)
        # send comments every 12 hours
        elif (
            self.ratio_calculator.comments < self.desired_comments
            and total_time > 43200
        ):
            logger.info(
                f"Video ID: {self.video_id} Ordering {self.desired_comments} comments for 12 hour interval"
            )
            comments = comments_db.head(n=5)
            # Split comments into chunks of 5
            comment_chunks = [
                "\r\n".join(comments.index[i : i + 5])
                for i in range(0, len(comments), 5)
            ]
            response = self.api.order(
                {
                    "service": 440,
                    "link": f"https://www.youtube.com/watch?v={self.video_id}",
                    "comments": comment_chunks[0],
                }
            )
            # Add the used comments to the used comments database
            used_comments = pd.concat([used_comments, comments])
            # Drop the used comments from the comments database
            comments_db.drop(comments.index, inplace=True)
            logger.info(f"Ordered comments: {response}")
            # Update the Google Sheet
            self.mark_comments_as_used(self.comments_sheet_id, used_comments)
            logger.info(
                f"Video ID: {self.video_id} Ordered comments: {response} for 12 hour interval"
            )
            total_time = 0
    
    def order_likes(self, last_views, min_views, total_time):
        if self.ratio_calculator.views - last_views >= min_views and self.ratio_calculator.likes < self.desired_likes:
            max_desired_likes = np.max(
                [
                    np.floor(
                        np.abs(
                            (1 - self.ratio_calculator.likes / self.desired_likes)
                            * (self.ratio_calculator.views - last_views)
                        )
                    ),
                    11,
                ]
            )
            # Use the video delta to determine how many comments to order
            likes = np.random.randint(10, int(max_desired_likes) if max_desired_likes > 10 else 10)
            logger.info(
                f"Ordering total of {likes} likes for {self.video_id}"
            )
            response = self.api.order(
                {
                    "service": 438,
                    "link": f"https://www.youtube.com/watch?v={self.video_id}",
                    "quantity": likes,
                }
            )
            logger.info(f"Video ID: {self.video_id} Ordered likes: {response}")
            # Sleep between sending batches of comments to simulate "drip" effect
            time.sleep(10800)
            total_time += 10800
            logger.info(f"Ordered likes: {response}")
        # send likes every 12 hours
        elif self.ratio_calculator.likes < self.desired_likes and total_time > 43200:
            logger.info(
                f"Video ID: {self.video_id} Ordering {self.desired_likes} likes for 12 hour interval"
            )
            likes = 15
            response = self.api.order(
                {
                    "service": 438,
                    "link": f"https://www.youtube.com/watch?v={self.video_id}",
                    "quantity": likes,
                }
            )
            logger.info(f"Ordered likes: {response}")
            total_time = 0

    def run(self, desired_views, campaign_data=None):
        """Run the campaign.

        Args:
            desired_views (int): The desired number of views for the video.
        """
        logger.info("Running campaign for video ID: %s", self.video_id)
        comments_db = self.get_comments()
        used_comments = pd.DataFrame(columns=["comments", "used"])
        min_views = 500
        total_time = 0
        # Update the views, likes, and comments
        self.ratio_calculator.get_views_likes_cmnts()
        last_views = None
        while not self.stop_flag.is_set():
            # Check the status of the campaign
            if self.data["Status"] != "Running":
                logger.info(
                    "Campaign completed or stopped for video ID: %s", self.video_id
                )
                break
            if comments_db is None:
                logger.error("No comments found")
                self.stop()
                break
            # If we ran out of comments to add, break the loop
            if comments_db.empty:
                logger.error("No comments left to add")
                self.stop()
                break
            # Update the views, likes, and comments
            self.ratio_calculator.get_views_likes_cmnts()
            self.desired_comments, self.desired_likes = (
                self.ratio_calculator.desired_views_likes(
                    self.genre, desired_views=desired_views
                )
            )
            logger.info(
                f"Current comments for {self.video_id}: {self.ratio_calculator.comments}, Desired comments: {self.desired_comments}"
            )
            logger.info(
                f"Current likes for {self.video_id}: {self.ratio_calculator.likes}, Desired likes: {self.desired_likes}"
            )
            if not last_views:
                last_views = self.ratio_calculator.views
            # If the video has less than the desired comments, order more comments
            logger.info(
                f"VideoID: {self.video_id} Current views: {self.ratio_calculator.views}, Last views: {last_views}"
            )
            self.order_comments(
                comments_db, last_views, min_views, comments_db, used_comments, total_time
            )

            self.order_likes(last_views,min_views, total_time)
            self.ratio_calculator.get_views_likes_cmnts()
            last_views = int(self.ratio_calculator.views)
            time.sleep(self.wait_time)
            total_time += self.wait_time
            logger.info(
                f"Video ID: {self.video_id} Sleeping for {self.wait_time} seconds"
            )

    def stop(self):
        logger.info("Stopping campaign for video ID: %s", self.video_id)
        self.stop_flag.set()  # Set the stop flag to stop the thread
        self.data["Status"] = "Completed"


if __name__ == "__main__":
    API_KEY = os.getenv("YOUTUBE_API_KEY")
    VIDEO_ID = "AfSjnsYiY_A"

    # Doesn't make sense to have to reintiailize in the campaign class
    try:
        calculator = YoutubeRatioCalc(API_KEY, VIDEO_ID)
        likes, comments, views = calculator.get_views_likes_cmnts()
    except Exception as e:
        logger.error(f"Error initializing calculator: {e}")
        raise e
    try:
        if likes is not None and comments is not None:
            comments_desired, likes_desired = calculator.desired_views_likes(
                "Hip Hop", views
            )
            campaign_data = {
                "Video ID": VIDEO_ID,
                "Genre": "Hip Hop",
                "Comments Sheet URL": "https://docs.google.com/spreadsheets/d/14cQjj5fm0v0GixnY0APFF6jM02V8ovOfqyPHubkpyBY",
                "Wait Time": 16,
                "Status": "Running",
            }
            campaign = Campaign(
                campaign_data,
                calculator,
                campaign_data["Comments Sheet URL"],
            )
            logger.info("Running campaign with desired views: %s", views)
            campaign.run(views)
        else:
            logger.error("Failed to retrieve video details")
    except Exception as e:
        logger.error(f"Error running campaign: {e}")
        raise e
