from instagrapi import Client
import inspect

try:
    print(inspect.getsource(Client.video_download_by_url))
except Exception as e:
    pass
