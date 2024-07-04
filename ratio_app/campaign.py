# Copyright (c) 2024, Artist Influence Development Team
# All rights reserved.

import os
import time

import numpy as np
import pandas as pd
import logging as log
from dotenv import load_dotenv
from googleapiclient.discovery import build
from jingle_smm import JingleSMM, MongoDB

load_dotenv()

logger = log.getLogger(__name__)
logger.setLevel(log.INFO)

class RatioCalculator:
    def __init__(self, api_key, video_id):
        self.api_key = api_key
        self.video_id = video_id
        self.video_details = None
        self.music_gsheet = "https://docs.google.com/spreadsheets/d/1k9A8viP4gFGjEwexNeLN6tmZyZ6YJIS_Ax6PxHjJvy8"
    
    @staticmethod
    def load_data(file_path: str):
        df = pd.read_csv(
            file_path,
            # Set first column as rownames in data frame
            index_col=0,
        )
        print(df.head())
        return df

    def get_video_details(self):
        """_summary_

        Returns:
            _type_: _description_
        """
        youtube = build("youtube", "v3", developerKey=self.api_key)
        request = youtube.videos().list(part="statistics", id=self.video_id)
        response = request.execute()

        if response["items"]:
            statistics = response["items"][0]["statistics"]
            likes = int(statistics.get("likeCount", "0"))
            comments = int(statistics.get("commentCount", "0"))
            views = int(statistics.get("viewCount", "0"))
            # Set the video details
            self.video_details = {"likes": likes, "comments": comments, "views": views}
            # Get genre
            print(response)
            return likes, comments, views
        else:
            return None, None, None

    def calculate_ratio(self, genre, metric):
        """_summary_

        Args:
            likes (_type_): _description_
            comments (_type_): _description_

        Returns:
            _type_: _description_
        """
        # To calculate the ratio we get the video details and genre
        df = self.load_data(self.music_gsheet+'/export?gid=1801952771&format=csv')
        # Get the genre ratio
        genre_ratio = df[df["genre"] == genre]
        # Create approximative polynomial of the requested metric vs ratio
        # We take the log of the views based on analysis revealing a logarithmic relationship between metrics vs views
        ratio = np.polyfit(np.log(genre_ratio["#views"]), genre_ratio[metric], 2)
        # Check the accuracy of the polynomial
        ratio_error = (
            np.polyval(np.log(genre_ratio[metric]), ratio) - genre_ratio[metric]
        )
        # If the error is too high we need to increase the degree of the polynomial
        if np.mean(ratio_error) > 0.1:
            ratio = np.polyfit(np.log(genre_ratio[metric]), genre_ratio[metric], 3)

        # Then we find the ratio for the current video
        ratio = np.polyval(ratio, views)

        # Apply some pseudo random noise to the ratio 
        ratio = ratio + np.random.Generator.random() / 1000
        return ratio

    def calculate_views_likes(self, genre):
        comments_to_views_ratio = self.calculate_ratio(genre, "comments")
        likes_to_views_ratio = self.calculate_ratio(genre, "likes")
        # Multiply the views by the ratio to get the number of comments and likes
        views = self.video_details["views"]
        comments = views * comments_to_views_ratio
        likes = views * likes_to_views_ratio
        return comments, likes


class Campaign:
    def __init__(self, data, wait_time=3600):
        self.data = data
        self.api = JingleSMM()
        self.video_id = data["video_id"]
        self.genre = data["genre"]
        self.comments = data["comments"]
        self.order_duration = data["order"]["duration"]
        self.current_comments = data["order"]["video"]["current_comments"]
        self.ratio_calculator = RatioCalculator(self.video_id)
        self.views = self.get_video_views()
        self.num_comments, self.num_likes = self.calculate_views_likes(self.genre)
        self.wait_time = wait_time
        self.split_comments = self.comments.split("\r\n")
        self.comment_batches = [[] for _ in range(self.order_duration)]

    @property
    def get_video_views(self):
        return self.ratio_calculator.get_video_details(self.video_id)[2]

    def _create_campaign_db(self, data):
        # This method should update the campaign database with the provided data
        # Replace with actual implementation
        for i, comment in enumerate(self.split_comments):
            batch_index = i % self.order_duration
            self.comment_batches[batch_index].append(comment)

    def _update_comments_db(self, comments, campaignId):
        client  = MongoDB().connect_mongo()
        comments_db = client.comments

        # check if comments length is greater than 300
        if (len(comments) > 300):
            # split the comments array into batches of 150 and update
            while len(comments) > 0:
                
                # shrink the
                comments = comments.sp
        else:
            comments_db.insert_one({
                    id: campaignId,
                    comments: comments,
            })
        
    
    def _update_likes_db(self, orders):
        # This method should update the likes database with the orders
        # Replace with actual implementation
        client  = MongoDB().connect_mongo()
        campaign_db = client.campaign
        # check if the campaign db exists
        campaign =  campaign_db.find({
            id: orders.id
        })
        if campaign: 
            campaign.desired_likes  = self.desired_likes
            campaign.current_likes  = orders["likes"]
        else:
            campaign_db.insert_one({
                id: orders["id"],
                "desired_likes": self.desired_likes,
                "current_likes": orders["likes"]
            })
    
        


    def run(self):
        self.comment_batches = self.create_drip_campaign(self.data)
        logger.info("Running campaign")
        while (self.current_comments < self.desired_comments) or (
            self.current_likes < self.desired_likes
        ):
            if self.current_comments < self.desired_comments:
                self.api.order(
                    {
                        "service": 1751,
                        "link": f"https://www.youtube.com/watch?v={self.video_id}",
                        "comments": self.comment_batches
                    }
                )
            if self.current_likes < self.desired_likes:
                self.api.order(
                    {
                        "service": 1751,
                        "link": f"https://www.youtube.com/watch?v={self.video_id}"
                    }
                )
            # Update the comments database
            self.update_comments_db(
                self.comment_batches[batch_index]
            )  # Update the comments database
            # update the likes database
            self.update_likes_db(self.comment_batches[batch_index])
            # update the campaign database in a cyclical pattern following US activity
            # get the current time in the US
            # get approximative usage for that time (peak usage ie has less wait_time)
            time.sleep(self.wait_time)

    def create_drip_campaign(self, data, *args, verbose=False):
        """Creates a drippable campaign which splices and stores comments in batch size NUM_COMMENTS
        and stores them to be ordered over a set time interval via a cronjob.
        Args:
            data (dict): Dictionary containing campaign data.
        Returns:
            None
        """
        # Determine the number of orders necessary
        views = self.get_video_views()
        order_duration = data["order"]["duration"]
        split_comments = data["comments"].split("\r\n")
        current_comments = data["order"]["video"]["current_comments"]        
        self.desired_comments = self.ratio_calculator.calculate_views_likes(self.genre)[
            0
        ]
        self.desired_likes = self.ratio_calculator.calculate_views_likes(self.genre)[1]
        if len(split_comments) + len(current_comments) < self.desired_comments:
            return "You need more comments"
        # Calculate the number of comments per hour
        num_comment_arrays = int(np.floor(len(split_comments) / order_duration))
        # Initialize an array to hold the batches




if __name__ == "__main__":
    API_KEY = os.getenv("YOUTUBE_API_KEY")
    VIDEO_ID = "f4eDOMk4ef0"

    calculator = RatioCalculator(API_KEY, VIDEO_ID)
    likes, comments, views = calculator.get_video_details()
    print(likes, comments, views)
    if likes is not None and comments is not None:
        ratio = calculator.calculate_ratio(likes, comments)
        print(
            f"Likes: {likes}, Comments: {comments}, Views: {views}, Like-to-Comment Ratio: {ratio}"
        )
    else:
        print("Failed to retrieve video details")
