# Copyright (c) 2024, Artist Influence Development Team
# All rights reserved.

import os
import time

import numpy as np
import requests
from dotenv import load_dotenv
from pymongo.mongo_client import MongoClient

load_dotenv()


class MongoDB:
    @staticmethod
    def connect_mongo(uri = os.getenv("MONGO_URI")):
        # Create a new client and connect to the server
        client = MongoClient(uri)

        # Send a ping to confirm a successful connection
        try:
            client.admin.command("ping")
            print("Pinged your deployment. You successfully connected to MongoDB!")
        except Exception as e:
            print(e)

        # use a database named "myDatabase"
        return client


class JingleSMM:
    def __init__(self, api_key=os.getenv("JINGLE_SMM_KEY")):
        self.api_url = "https://jinglesmm.com/api/v2"
        self.api_key = api_key

    def drip_engagement(self, video_url, comments):
        """This function will post engagement to the API

        Args:
            video_url (_type_): _description_
            comments (_type_): _description_
        """
        for comment in comments:
            response = requests.post(
                self.api_url,
                data={"video_url": video_url, "likes": 1, "comment": comment},
            )
            if response.status_code != 200:
                print(f"Failed to post engagement for {video_url}")
            time.sleep(1)

    def order(self, data):
        post = {"key": self.api_key, "action": "add", **data}
        response = self.connect(post)
        self._update_comments_db(response)
        return response

    def _update_comments_db(self, response):
        # Add order to MongoDB
        db = MongoDB().connect_mongo()
        db = db.jingle_smm
        orders = db.orders
        # Get the order status
        order_status = self.status(response["order"])
        orders.insert_one({id: response["order"]})

        for i in response["data"]:
            # Update the order status
            orders.update_one(
                {"id": response["order"]},
                {
                    "$set": {
                        "status": order_status["status"],
                        "comments": order_status["comments"],
                    },
                    "drip_time": time.time() + "1hr",
                },
            )

    def status(self, order_id):
        return self.connect(
            {"key": self.api_key, "action": "status", "order": order_id}
        )

    def multiStatus(self, order_ids):
        return self.connect(
            {
                "key": self.api_key,
                "action": "status",
                "orders": ",".join(map(str, order_ids)),
            }
        )

    def services(self):
        return self.connect(
            {
                "key": self.api_key,
                "action": "services",
            }
        )

    def refill(self, orderId):
        return self.connect(
            {
                "key": self.api_key,
                "action": "refill",
                "order": orderId,
            }
        )

    def multiRefill(self, orderIds):
        return self.connect(
            {
                "key": self.api_key,
                "action": "refill",
                "orders": ",".join(map(str, orderIds)),
            }
        )

    def refillStatus(self, refillId):
        return self.connect(
            {
                "key": self.api_key,
                "action": "refill_status",
                "refill": refillId,
            }
        )

    def multiRefillStatus(self, refillIds):
        return self.connect(
            {
                "key": self.api_key,
                "action": "refill_status",
                "refills": ",".join(map(str, refillIds)),
            }
        )

    def cancel(self, orderIds):
        return self.connect(
            {
                "key": self.api_key,
                "action": "cancel",
                "orders": ",".join(map(str, orderIds)),
            }
        )

    def balance(self):
        return self.connect(
            {
                "key": self.api_key,
                "action": "balance",
            }
        )


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

        # Determine the number of comments and likes necessary
        genre_ratio = self.GENRE_RATIO.get(data["genre"], (1, 1))
        num_comments, num_likes = views * genre_ratio[0], views * genre_ratio[1]

        order_duration = data["order"]["duration"]
        split_comments = data["comments"].split("\r\n")
        current_comments = data["order"]["video"]["current_comments"]

        if len(split_comments) + len(current_comments) < num_comments:
            return "You need more comments"

        # Calculate the number of comments per hour
        num_comment_arrays = int(np.floor(len(split_comments) / order_duration))

        # Initialize an array to hold the batches
        comment_batches = [[] for _ in range(order_duration)]

        # Distribute the comments into the batches
        for i, comment in enumerate(split_comments):
            batch_index = i % order_duration
            comment_batches[batch_index].append(comment)

        # Optional: Display the result
        if verbose:
            for hour, batch in enumerate(comment_batches):
                print(f"Hour {hour + 1}: {len(batch)} comments")

        # Update the database with the campaign information
        self._create_campaign_db(data)
        self._update_comments_db(comment_batches)
        self._update_likes_db(comment_batches)
        return None

    def cron_job(self, video_id):
        """Cron job to submit comments and likes to JingleSMM API.

        Args:
            video_id (str): The ID of the video for which to submit comments and likes.
        """
        # Get the relevant comments for the video_id
        comments = self.get_comments_for_video(video_id)

        # Distribute comments and likes over time
        for hour, comment_batch in enumerate(comments):
            print(f"Submitting batch for hour {hour + 1}")
            self.drip_engagement(video_id, comment_batch)
            time.sleep(
                3600 + np.random.random(400, 900)
            )  # Sleep for 1 hour with some variance before submitting the next batch

    def connect(self, post):
        response = requests.post(self.api_url, data=post)
        print(response, "response")
        if response.status_code == 200:
            return response.json()
        else:
            return response.json()

    def get_all_orders(self):
        db = self._connect_mongo()
        orders = db.orders

        # Update the order status
        orders.update_one(
            {"id": response["order"]},
            {"$set": {"status": order_status["status"]}},
        )

        # Get all orders from MongoDB
        return orders.find()


# api = Api(api_key=os.environ['JINGLE_SMM_API_KEY'])

if __name__ == "__main__":
    api = JingleSMM()

    # Fetch all services
    services = api.services()

    # Fetch user balance
    balance = api.balance()

    # # Add order
    # order = api.order(
    #     {
    #         "service": 1751,
    #         "link": "https://www.youtube.com/watch?v=puHMGZIMXNE",
    #         "comments": "Absolutely 🔥. This song bangs so hard, 💜 it.\r\nHoy Fred Again está en Colombia Bogotá me parte el corazón no poder está en ese concierto...asi que está noche lo viviré con sus músicas ❤\r\nEfectivamente señores revivió la música electrónica 🧐🚬🍷🤌🏻\r\nOmg this song gives me shivers! Wow what an absolute tune! 🎉\r\nHermosa cancion!!! Emocionante y emocional!!❤❤\r\nI simply haven’t got the words to describe how beautiful this is\r\nSoo good fair play keep these incredible tune coming 👏 🙌 ❤\r\nMas que som espetacular 🔥💃❤‍🔥\r\nLogran transportar. ¡La mente estalla! 🔥😎🎶\r\nSounds Like it belongs in an awesome anime right up there with inner universe\r\nThis song is incredible, mind-blowing 🤯. I could listen it for a thousand times and still wanna hear it. 🤯\r\nWelch eine Mega Nummer: Sanft und weich am Anfang, gute Stimme und mit Klavier und Geige, das geht voll ab bei mir ! Danke dafür :)\r\nMisericórdiaaa que música Fenomenal 👏🏻👏🏻👏🏻👏🏻\r\nMuito massa essa música... Só a entrada com o violino vc se encanta 🇧🇷🇧🇷🇧🇷🇧🇷🇧🇷🇧🇷\r\nWhat a song!! ❤",
    #     }
    # )

    # if "error" in order:
    #     print("Error: " + order["error"])
    # else:
    #     print(order)

    # # Check order status
    # status = api.status(order["order"])

    # if "error" in status:
    #     print("Error: " + status["error"])
    # else:
    #     print("Status: " + status["status"])

    # print("Balance: " + balance["balance"])
