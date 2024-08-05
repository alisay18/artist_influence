# Copyright (c) 2024, Artist Influence Development Team
# All rights reserved.

import logging as log
import os
import threading
import time

import numpy as np
import pandas as pd
from dotenv import load_dotenv
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
        self.damper = 0.2
        self.video_id = data["Video ID"]
        self.genre = data["Genre"]
        self.comments_sheet = comment_sheet
        self.ratio_calculator: YoutubeRatioCalc = ratio_calculator
        self.wait_time = wait_time
        self.stop_flag = threading.Event()  # Add a stop flag

    def get_comments(self):
        if self.comments_sheet:
            comments = load_data(
                self.comments_sheet + "/export?format=csv",
                {"comments": "str", "video_link": "str"},
            )
            return comments
        else:
            return None

    def run(self, desired_views):
        """Run the campaign.

        Args:
            desired_views (int): The desired number of views for the video.
        """
        logger.info("Running campaign for video ID: %s", self.video_id)
        comments_db = self.get_comments()
        used_comments = pd.DataFrame(columns=["comments", "video_link"])
        view_last_hour = None
        while not self.stop_flag.is_set():
            # Check the status of the campaign
            if self.data["Status"] != "Running":
                logger.info(
                    "Campaign completed or stopped for video ID: %s", self.video_id
                )
                break

            # Update the views, likes, and comments
            self.ratio_calculator.get_views_likes_cmnts()
            self.desired_comments, self.desired_likes = (
                self.ratio_calculator.desired_views_likes(
                    self.genre, desired_views=desired_views
                )
            )
            logger.info(
                f"Current comments: {self.ratio_calculator.comments}, Desired comments: {self.desired_comments}"
            )

            if comments_db is None:
                logger.error("No comments found")
                break
            # If we ran out of comments to add, break the loop
            if comments_db.index.equals(used_comments.index):
                logger.error("No comments left to add")
                # See if we can order more comments
                comments_db = self.get_comments()
                # Remove the used comments
                comments_db = comments_db.drop(used_comments.index)
                if comments_db.index.equals(used_comments.index):
                    logger.error("No comments left to add")
                    break

            if not view_last_hour:
                view_last_hour = self.ratio_calculator.views + 10
            # If the video has less than the desired comments, order more comments
            if view_last_hour - self.ratio_calculator.views >= 10:
                # Use the video delta to determine how many comments to order
                diff = np.floor(
                    np.abs(
                        (self.ratio_calculator.comments / self.desired_comments)
                        * (view_last_hour - self.ratio_calculator.views) * self.damper
                    )
                )
                comments = comments_db.sample(n=int(diff) if diff > 5 else 6)
                comment = "\r\n".join(comments.index)
                logger.info(f"Ordering {comments.shape[0]} comments")
                response = self.api.order(
                    {
                        "service": 1751,
                        "link": f"https://www.youtube.com/watch?v={self.video_id}",
                        "comments": comment,
                    }
                )
                # Add the used comments to the used comments database
                used_comments = comments_db.loc[comments.index]
                # Drop the used comments from the comments database
                comments_db.drop(comments.index)
                logger.info(f"Ordered comments: {response}")
            view_last_hour = self.ratio_calculator.views
            time.sleep(self.wait_time)

    def stop(self):
        self.stop_flag.set()  # Set the stop flag to stop the thread


if __name__ == "__main__":
    API_KEY = os.getenv("YOUTUBE_API_KEY")
    VIDEO_ID = "AfSjnsYiY_A"

    # Doesn't make sense to have to reintiailize in the campaign class
    calculator = YoutubeRatioCalc(API_KEY, VIDEO_ID)
    likes, comments, views = calculator.get_views_likes_cmnts()

    if likes is not None and comments is not None:
        comments_desired, likes_desired = calculator.desired_views_likes(
            "Hip Hop", views
        )
        campaign_data = {
            "Video ID": VIDEO_ID,
            "Genre": "Hip Hop",
            "Comments Sheet URL": "https://docs.google.com/spreadsheets/d/14cQjj5fm0v0GixnY0APFF6jM02V8ovOfqyPHubkpyBY",
            "Wait Time": 36,
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
