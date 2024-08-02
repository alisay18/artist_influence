import datetime
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
        channel_id,
        music_gsheet="https://docs.google.com/spreadsheets/d/1k9A8viP4gFGjEwexNeLN6tmZyZ6YJIS_Ax6PxHjJvy8",
    ):
        self.api_key = api_key
        self.video_id = video_id
        self.channel_id = channel_id
        self.video_details = None
        self.music_gsheet = music_gsheet
        self.likes, self.comments, self.views = self.get_views_likes_cmnts()

    def get_view_count_one_hour_ago(self):
        try:
            # Get the current time and one hour ago
            now = datetime.datetime.now()
            one_hour_ago = now - datetime.timedelta(hours=1)

            # Format dates for the API request
            end_date = now.strftime("%Y-%m-%d")
            start_date = one_hour_ago.strftime("%Y-%m-%d")

            youtube = build(
                "youtubeAnalytics",
                "v2",
                credentials="AIzaSyAvDxRgNPabecOKhb724DmJQy6k19x6Ji8",
            )
            # Make the Analytics API request
            request = youtube.reports().query(
                ids=f"channel=={self.channel_id}",
                startDate=start_date,
                endDate=end_date,
                metrics="views",
                dimensions="video",
                filters=f"video=={self.video_id}",
                sort="-views",
            )
            response = request.execute()

            # Parse the response
            if response.get("rows"):
                view_count = response["rows"][0][1]
                return int(view_count)
            else:
                print("No data found for the specified video and time range.")
                return None

        except Exception as e:
            print(f"An error occurred: {str(e)}")
            return None

    def get_views_likes_cmnts(self):
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
                        * (view_last_hour - self.ratio_calculator.views)
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
    CHANNEL_ID = "UCTKTRVaWrythRIGNfZYBp2A"

    # Doesn't make sense to have to reintiailize in the campaign class
    calculator = YoutubeRatioCalc(API_KEY, VIDEO_ID, CHANNEL_ID)
    likes, comments, views = calculator.get_views_likes_cmnts()

    if likes is not None and comments is not None:
        comments_desired, likes_desired = calculator.desired_views_likes(
            "Hip Hop", views
        )
        campaign_data = {
            "Video ID": VIDEO_ID,
            "Channel ID": CHANNEL_ID,
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
