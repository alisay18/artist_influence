from googleapiclient.discovery import build
import os
from dotenv import load_dotenv
import time
import requests

load_dotenv()

class RatioCalculator:
    def __init__(self, api_key, video_id):
        self.api_key = api_key
        self.video_id = video_id

    def get_video_details(self):
        """_summary_

        Returns:
            _type_: _description_
        """
        youtube = build('youtube', 'v3', developerKey=self.api_key)
        request = youtube.videos().list(
            part="statistics",
            id=self.video_id
        )
        response = request.execute()

        if response['items']:
            statistics = response['items'][0]['statistics']
            likes = int(statistics.get('likeCount', '0'))
            comments = int(statistics.get('commentCount', '0'))
            views = int(statistics.get('viewCount', '0'))
            return likes, comments, views
        else:
            return None, None, None

    def drip_engagement(self, video_url, comments, api_url="https://jingle-smm-api.com/drip" ):
        """_summary_

        Args:
            video_url (_type_): _description_
            comments (_type_): _description_
        """
        for comment in comments:
            response = requests.post(api_url, data={"video_url": video_url, "likes": 1, "comment": comment})
            if response.status_code != 200:
                print(f"Failed to post engagement for {video_url}")
            time.sleep(1)

    @staticmethod
    def calculate_ratio(likes, comments):
        """_summary_

        Args:
            likes (_type_): _description_
            comments (_type_): _description_

        Returns:
            _type_: _description_
        """
        if comments == 0:
            return float('inf')
        return likes / comments

if __name__ == '__main__':
    API_KEY = os.getenv('YOUTUBE_LIKES_COMMENTS_KEY')
    VIDEO_ID = 'f4eDOMk4ef0'
    
    calculator = RatioCalculator(API_KEY, VIDEO_ID)
    likes, comments, views = calculator.get_video_details()

    if likes is not None and comments is not None:
        ratio = calculator.calculate_ratio(likes, comments)
        print(f"Likes: {likes}, Comments: {comments}, Views: {views}, Like-to-Comment Ratio: {ratio}")
    else:
        print("Failed to retrieve video details")
