from google.cloud import speech
import setting
import os
import io
from gcloud import storage


os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = setting.AUTH_JSON_PATH


def upload_blob(source_file_name, destination_blob_name):

    storage_client = storage.Client()
    bucket = storage_client.bucket('kirinuki_hiroyuki')
    blob = bucket.blob(destination_blob_name)

    blob.upload_from_filename(source_file_name)

    print(
        "File {} uploaded to {}.".format(
            source_file_name, destination_blob_name
        )
    )

def transcribe_gcs(gcs_uri):
    """Asynchronously transcribes the audio file specified by the gcs_uri."""

    client = speech.SpeechClient()

    audio = speech.RecognitionAudio(uri=gcs_uri)
    config = speech.RecognitionConfig(
        encoding=speech.RecognitionConfig.AudioEncoding.FLAC,
        sample_rate_hertz=44100,
        language_code="ja-JP",
        audio_channel_count=2,
    )

    operation = client.long_running_recognize(config=config, audio=audio)

    print("Waiting for operation to complete...")
    response = operation.result(timeout=90)

    ret_str = []

    for result in response.results:
        ret_str.append(result.alternatives[0].transcript)
    
    return ret_str
