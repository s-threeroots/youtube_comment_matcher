from googleapiclient import discovery, errors
import google_auth_oauthlib.flow
from bs4 import BeautifulSoup
import ast
import requests
import requests_html
import os
import re
import sys
import youtube_dl
import setting


# Set DEVELOPER_KEY to the API key value from the APIs & auth > Registered apps
# tab of
#   https://cloud.google.com/console
# Please ensure that you have enabled the YouTube Data API for your project.
YOUTUBE_API_SERVICE_NAME = "youtube"
YOUTUBE_API_VERSION = "v3"
YOUTUBE_URL = "https://www.youtube.com"

def auth():
    youtube = discovery.build(YOUTUBE_API_SERVICE_NAME,
                              YOUTUBE_API_VERSION, developerKey=setting.DEVELOPER_KEY)
    return youtube


def getVideoData(youtube, options):

    # Call the search.list method to retrieve results matching the specified
    # query term.
    search_response = youtube.search().list(
        q=options.q,
        part="id,snippet",
        maxResults=options.max_results,
        channelId=options.channel_id,
        order='date'
    ).execute()

    videos = []

    # Add each result to the appropriate list, and then display the lists of
    # matching videos, channels, and playlists.
    for search_result in search_response.get("items", []):
        if search_result["id"]["kind"] == "youtube#video":
            videos.append("%s (%s)" % (search_result["snippet"]["title"],
                                       search_result["id"]["videoId"]))

    print("Videos:\n", "\n".join(videos), "\n")

    return videos


def getAudioFromVideo(video_id):

    url = YOUTUBE_URL + '/watch?v=' + video_id
    output_file = setting.TMP_FILE_DIR + "audio" + '.%(ext)s'

    ydl_opts = {
        'outtmpl': output_file,
        #'format': 'bestaudio/best',
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'flac',
        }],
    }

    ydl = youtube_dl.YoutubeDL(ydl_opts)
    info_dict = ydl.extract_info(url, download=True)

    return output_file


def getCommentData(video_id):
    # Set up variables for requests.
    target_url = YOUTUBE_URL + "/watch?v=" + video_id
    dict_str = ''
    next_url = ''
    comment_data = []
    session = requests_html.HTMLSession()
    headers = {
        'user-agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_5) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/80.0.3987.163 Safari/537.36'}

    # Get the video page.
    resp = session.get(target_url)
    resp.html.render(sleep=3)

    # Retrieve the title and sanitize so it is a valid filename.
    title = resp.html.find('title')
    title = title[0].text.replace(' - YouTube', '')
    title = get_valid_filename(title)

    print(title)

    # Regex match for emoji.
    RE_EMOJI = re.compile('[\U00010000-\U0010ffff]', flags=re.UNICODE)

    # Find any live_chat_replay elements, get URL for next live chat message.
    for iframe in resp.html.find("iframe"):
        if "live_chat_replay" in iframe.attrs["src"]:
            next_url = "".join([YOUTUBE_URL, iframe.attrs["src"]])

    if not next_url:
        print("Couldn't find live_chat_replay iframe. Maybe try running again?")
        sys.exit(1)

    # TODO - We should fail fast if next_url is empty, otherwise you get error:
    # Invalid URL '': No schema supplied. Perhaps you meant http://?

    # TODO - This loop is fragile. It loops endlessly when some exceptions are hit.
    while(1):

        try:
            html = session.get(next_url, headers=headers)
            soup = BeautifulSoup(html.text, 'lxml')

            # Loop through all script tags.
            for script in soup.find_all('script'):
                script_text = str(script)
                if 'ytInitialData' in script_text:
                    dict_str = ''.join(script_text.split(" = ")[1:])

            # Capitalize booleans so JSON is valid Python dict.
            dict_str = dict_str.replace("false", "False")
            dict_str = dict_str.replace("true", "True")

            # Strip extra HTML from JSON.
            dict_str = re.sub(r'};.*\n?.*<\/script>', '}', dict_str)

            # Correct some characters.
            dict_str = dict_str.rstrip("  \n;")

            # TODO: I don't seem to have any issues with emoji in the messages.
            dict_str = RE_EMOJI.sub(r'', dict_str)

            # Evaluate the cleaned up JSON into a python dict.
            dics = ast.literal_eval(dict_str)

            # TODO: On the last pass this returns KeyError since there are no more
            # continuations or actions. Should probably just break in that case.
            continue_url = dics["continuationContents"]["liveChatContinuation"][
                "continuations"][0]["liveChatReplayContinuationData"]["continuation"]
            print('Found another live chat continuation:')
            print(continue_url)
            next_url = "https://www.youtube.com/live_chat_replay?continuation=" + continue_url

            # Extract the data for each live chat comment.
            for samp in dics["continuationContents"]["liveChatContinuation"]["actions"]:

                # 全コメは重いのでスパチャだけ抽出する
                if "replayChatItemAction" in samp and 'actions' in samp["replayChatItemAction"] and 'addChatItemAction' in samp["replayChatItemAction"]["actions"][0]:
                    if 'liveChatPaidMessageRenderer' in samp["replayChatItemAction"]["actions"][0]['addChatItemAction']['item']:
                        comment_data.append(str(samp))

        except requests.ConnectionError:
            print("Connection Error")
            continue
        except requests.HTTPError:
            print("HTTPError")
            break
        except requests.Timeout:
            print("Timeout")
            continue
        except requests.exceptions.RequestException as e:
            print(e)
            break
        except KeyError as e:
            error = str(e)
            if 'liveChatReplayContinuationData' in error:
                print('Hit last live chat segment, finishing job.')
            else:
                print("KeyError")
                print(e)
            break
        except SyntaxError as e:
            print("SyntaxError")
            print(e)
            break
            # continue #TODO
        except KeyboardInterrupt:
            break
        except Exception:
            print("Unexpected error:" + str(sys.exc_info()[0]))

    return comment_data
