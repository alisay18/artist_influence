# Copyright (c) 2024, Artist Influence Development Team
# All rights reserved.

import os
import time

import numpy as np
import requests
from dotenv import load_dotenv

load_dotenv()


class JingleSMM:
    def __init__(self, api_key=os.getenv("JINGLE_SMM_KEY")):
        self.api_url = "https://jinglesmm.com/api/v2"
        self.api_key = api_key

    def drip_engagement(self, video_url, comments):
        """This function will post engagement to the API

        Args:
            video_url (str): The URL of the video to post engagement for
            comments (list): A list of comments to post
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
        """This function will post an order to the API

        Args:
            data (json): A JSON object containing the order data

        Returns:
            json: The response from the API
        """
        post = {"key": self.api_key, "action": "add", **data}
        response = self.connect(post)
        # self._update_comments_db(response)
        return response

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

    def connect(self, post):
        response = requests.post(self.api_url, data=post)
        print(response, "response")
        if response.status_code == 200:
            return response.json()
        else:
            return response.json()


# api = Api(api_key=os.environ['JINGLE_SMM_API_KEY'])

if __name__ == "__main__":
    api = JingleSMM()

    # Fetch all services
    services = api.services()

    # Fetch user balance
    balance = api.balance()

    # # Add order
    order = api.order(
        {
            "service": 1751,
            "link": "https://www.youtube.com/watch?v=puHMGZIMXNE",
            "comments": "Absolutely 🔥. This song bangs so hard, 💜 it.\r\nHoy Fred Again está en Colombia Bogotá me parte el corazón no poder está en ese concierto...asi que está noche lo viviré con sus músicas ❤\r\nEfectivamente señores revivió la música electrónica 🧐🚬🍷🤌🏻\r\nOmg this song gives me shivers! Wow what an absolute tune! 🎉\r\nHermosa cancion!!! Emocionante y emocional!!❤❤\r\nI simply haven’t got the words to describe how beautiful this is\r\nSoo good fair play keep these incredible tune coming 👏 🙌 ❤\r\nMas que som espetacular 🔥💃❤‍🔥\r\nLogran transportar. ¡La mente estalla! 🔥😎🎶\r\nSounds Like it belongs in an awesome anime right up there with inner universe\r\nThis song is incredible, mind-blowing 🤯. I could listen it for a thousand times and still wanna hear it. 🤯\r\nWelch eine Mega Nummer: Sanft und weich am Anfang, gute Stimme und mit Klavier und Geige, das geht voll ab bei mir ! Danke dafür :)\r\nMisericórdiaaa que música Fenomenal 👏🏻👏🏻👏🏻👏🏻\r\nMuito massa essa música... Só a entrada com o violino vc se encanta 🇧🇷🇧🇷🇧🇷🇧🇷🇧🇷🇧🇷\r\nWhat a song!! ❤",
        }
    )

    if "error" in order:
        print("Error: " + order["error"])
    else:
        print(order)

    # Check order status
    status = api.status(order["order"])

    if "error" in status:
        print("Error: " + status["error"])
    else:
        print("Status: " + status["status"])

    print("Balance: " + balance["balance"])
