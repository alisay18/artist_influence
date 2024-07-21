# Copyright (c) 2024, Artist Influence Development Team
# All rights reserved.

import os
import time
import random

import numpy as np
import pandas as pd
import logging as log
from dotenv import load_dotenv
from googleapiclient.discovery import build
from jingle_smm import JingleSMM, MongoDB
from datetime import datetime


load_dotenv()

logger = log.getLogger(__name__)
logger.setLevel(log.INFO)


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


class RatioCalculator:
    def __init__(self, api_key, video_id):
        self.api_key = api_key
        self.video_id = video_id
        self.video_details = None
        self.music_gsheet = "https://docs.google.com/spreadsheets/d/1k9A8viP4gFGjEwexNeLN6tmZyZ6YJIS_Ax6PxHjJvy8"


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
            print(response, self.video_details)
            
            return likes, comments, views
        else:
            return None, None, None

    def calculate_ratio(self, metric, views_arr, df):
        """_summary_

        Args:
            likes (_type_): _description_
            comments (_type_): _description_

        Returns:
            _type_: _description_
        """
        # Create approximative polynomial of the requested metric vs ratio
        # We take the log of the views based on analysis revealing a logarithmic relationship between metrics vs views
        ratio_eq = np.polyfit(
            np.log(np.array(views_arr)), np.log(np.array(df[metric])), 1
        )
        # Check the accuracy of the polynomial
        ratio_error = 1 - np.sum(
            (np.polyval(ratio_eq, np.log(views_arr)) - np.log(df[metric])) ** 2
        ) / np.sum((np.log(df[metric]) - np.mean(np.log(df[metric]))) ** 2)
        # If the error is too high we need to increase the degree of the polynomial for now.
        if ratio_error < 0.80:
            ratio_eq = np.polyfit(np.log(views_arr), np.log(df[metric]), 3)
        # return the polynomial
        return np.poly1d(ratio_eq)

    def calculate_views_likes(self, genre, desired_views=None):
        # To calculate the ratio we get the video details and genre
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
        # Get the genre ratio
        genre_splice = df[df["genre"] == genre]
        comments_to_views_ratio = self.calculate_ratio(
            "#comments", genre_splice["#views"], genre_splice
        )
        likes_to_views_ratio = self.calculate_ratio(
            "#likes", genre_splice["#views"], genre_splice
        )
        # Multiply the views by the ratio to get the number of comments and likes
        views = self.video_details["views"] + desired_views
        comments = np.e ** (comments_to_views_ratio(np.log(views)))
        likes = np.e ** (likes_to_views_ratio(np.log(views)))
        return comments, likes


class Campaign:
    def __init__(self, data, wait_time=3600):
        self.data = data
        self.api = JingleSMM()
        self.video_id = data["video_id"]
        self.genre = data["genre"]
        self.comments_sheet = "https://docs.google.com/spreadsheets/d/14cQjj5fm0v0GixnY0APFF6jM02V8ovOfqyPHubkpyBY"
        self.ratio_calculator = RatioCalculator(API_KEY, self.video_id)
        self.wait_time = wait_time

    @property
    def get_video_views(self):
        _,_,views =  self.ratio_calculator.get_video_details()
        
        return  views

    @property
    def get_video_comments(self):
        _,comments, _ =  self.ratio_calculator.get_video_details()
        return  comments

    
    @property
    def get_video_likes(self):
        likes, _, _ =  self.ratio_calculator.get_video_details()
        return  likes

    def get_comments(self):
        if (self.comments_sheet):
            comments = load_data(
                self.comments_sheet + "/export?gid=0&format=csv",
                {"comments": "str",
                "video_link": "str"}
            )
            return comments
        else:
            return None
        
    def _update_comments_db(self, split_comments, NUM_COMMENTS=50,campaign_id=None):
        client = MongoDB().connect_mongo()
        # Calculate the number of comments per hour
        num_comment_arrays = int(np.floor(len(split_comments) / NUM_COMMENTS))
        # create an array to hold the batches
        def pop_first_n_strings(lst, n):
            # Extract the first n elements
            popped_elements = lst[:n]
            # Delete the first n elements from the original list
            del lst[:n]
            return popped_elements
        # Create a list to hold the batches
        comment_batches = []
        # Pop the first NUM_COMMENTS comments into a mongoDB collection
        for _ in range(num_comment_arrays):
            comment_batches.append(pop_first_n_strings(split_comments, NUM_COMMENTS))
        # Add the remaining comments to the last batch
        comment_batches.append(split_comments)
        # Create a collection to hold the comments
        comments = client.comments
        # Insert the comments into the collection
        comments.insert_many(
            [
                {
                    "video_id": self.video_id,
                    "comment": comment,
                    "created_at": datetime.utcnow(),
                    "updated_at": datetime.utcnow(),
                    "campaign_id": campaign_id,
                    "order": idx
                }
                for idx, comment in enumerate(comment_batches[0])
            ]
        )
        # Read in the comments and pop the first NUM_COMMENTS comments into a mongoDB collection
        client.close()
        return comment_batches

    def run(self, desired_views):
        # comments, new_campaign, campaign_id = self.create_drip_campaign(desired_views)
        # logger.info("Running campaign")
        # idx = new_campaign.order
        # for batch_index, comment in enumerate(comments):
        for _ in range(20):
            # Get the desired number of comments 
            self.ratio_calculator.get_video_details()
            self.desired_comments, self.desired_likes = self.ratio_calculator.calculate_views_likes(self.genre, desired_views=desired_views)
            print(f'Current comments: {self.get_video_comments}, Desired comments: {self.desired_comments}')
            if (self.get_video_comments < self.desired_comments):
                print("Ordering comments")
                # Get self.desired_comments - self.current_comments
                diff =np.floor(np.abs(self.desired_comments- self.get_video_comments)/100)
                comments_db  = self.get_comments()
                comments = comments_db.sample(n=int(diff) if diff > 5 else 6)
                comment = "\r\n".join(comments.index)
                # Order the comments
                # strip commas 

                response =  self.api.order(
                        {
                            "service": 1751,
                            "link": f"https://www.youtube.com/watch?v={self.video_id}",
                            "comments": comment
                        }
                )
                # remove the comments from the database
                comments_db.drop(comments.index)
                print(response)
            # if self.current_likes < self.desired_likes:
            #     self.api.order(
            #         {
            #             "service": 1751,
            #             "link": f"https://www.youtube.com/watch?v={self.video_id}",
            #         }
            #     )
            # Update the comments database
            # self.update_comments_db(
            #     self.comment_batches[batch_index]
            # )  # Update the comments database
            # update the likes database
            # self.update_likes_db(self.comment_batches[batch_index])
            # update the campaign database in a cyclical pattern following US activity
            # get the current time in the US
            # get approximative usage for that time (peak usage ie has less wait_time)
            time.sleep(self.wait_time)

    # def create_drip_campaign(self, desired_views, NUM_COMMENTS=50):
    #     """Creates a drippable campaign which splices and stores comments in batch size NUM_COMMENTS
    #     and stores them to be ordered over a set time interval via a cronjob.
    #     Args:
    #         data (dict): Dictionary containing campaign data.
    #     Returns:
    #         None
    #     """
    #     # Determine the number of orders necessary
    #     views = self.get_video_views()
    #     split_comments = self.data["comments"].split("\r\n")
    #     current_comments = self.data["order"]["video"]["current_comments"]
    #     self.desired_comments, self.desired_likes = (
    #         self.ratio_calculator.calculate_views_likes(self.genre, desired_views=desired_views)
    #     )
    #     if len(split_comments) + len(current_comments) < self.desired_comments:
    #         # hack to add more comments
    #         # get the difference between the desired comments and the current comments
    #         diff = np.abs(self.desired_comments - len(split_comments))
    #         # set the number of comments to be added
    #         self.desired_comments = len(current_comments) + diff
    #     def get_unique_campaign_id():
    #         while True:
    #             new_id = random.randint(10000, 99999)
    #             if not campaign.find_one({"campaign_id": new_id}):
    #                 return new_id

    #     client = MongoDB().connect_mongo()
    #     campaign = client.campaign
    #     campaign.create_index("campaign_id", unique=True)
    #     campaign_id = get_unique_campaign_id()
    #     new_campaign = campaign.insert_one(
    #         {
    #             "video_id": self.video_id,
    #             "desired_views": desired_views,
    #             "desired_comments": self.desired_comments,
    #             "desired_likes": self.desired_likes,
    #             "current_comments": current_comments,
    #             "current_likes": self.get_video_likes(),
    #             "submitted_likes": 0,
    #             "created_at": datetime.utcnow(),
    #             "updated_at": datetime.utcnow(),
    #             "campaign_id": campaign_id,
    #             "order": 0           
    #         }
    #     )
    #     comments = self._update_comments_db(split_comments, NUM_COMMENTS, campaign_id)
    #     return comments, new_campaign, campaign_id




if __name__ == "__main__":
    API_KEY = os.getenv("YOUTUBE_API_KEY")
    VIDEO_ID = "AfSjnsYiY_A"

    calculator = RatioCalculator(API_KEY, VIDEO_ID)
    likes, comments, views = calculator.get_video_details()
    print(likes, comments, views)
    if likes is not None and comments is not None:
        comments_desired, likes_desired = calculator.calculate_views_likes("Hip Hop", views)
        # Run the campaign
        campaign = Campaign(
            {
                "video_id": VIDEO_ID,
                "genre": "Hip Hop",
                
            }
        )
        print("Running campaign with desired views", views)
        campaign.run(views)
        # print(
        #     f"Likes: {likes}, Comments: {comments_desired}, Views: {likes_desired}"
        # )
    else:
        print("Failed to retrieve video details")
