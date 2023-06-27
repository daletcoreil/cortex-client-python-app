import os
import time
import json
import boto3 as boto3
import cortex_client
from botocore.config import Config
from cortex_client import Configuration, Locator, VideoAnalysisInput, \
    Job, JobMediatorInput, Token, AuthApi, JobsApi, \
    MediatorJob, JobMediatorStatus, SpeechToTextOutput, SpeechToTextInput
from cortex_client.rest import ApiException
from pprint import pprint

# Read configuration from json file.
with open(os.environ['APP_CONFIG_FILE']) as json_file:
    config_file = json.load(json_file)

mediator_config = Configuration()
if 'host' in config_file:
    mediator_config.host = config_file['host']


client = config_file['clientKey']
secret = config_file['clientSecret']
project_service_id = config_file['projectServiceId']

aws_access_key_id = config_file['aws_access_key_id']
aws_secret_access_key = config_file['aws_secret_access_key']
region_name = config_file['bucketRegion']
language_code = config_file['language_code']

#aws_session_token = config_file['aws_session_token']

# Create an S3 client
# https://github.com/boto/boto3/issues/1644
# This is very important to initialize s3 client with region name, addressing_style & signature_version
s3 = boto3.client('s3', aws_access_key_id=aws_access_key_id, aws_secret_access_key=aws_secret_access_key, region_name=region_name, config=Config(s3={'addressing_style': 'path'}, signature_version='s3v4'))

# input & output data
bucketName = config_file['bucketName']

inputFile = config_file['localPath'] + config_file['inputFile']
inputKey = config_file['inputFile']

outputFile_json = config_file['localPath'] + config_file['outputFile_json']
outputKey_json = config_file['outputFile_json']

outputFile_ttml = config_file['localPath'] + config_file['outputFile_ttml']
outputKey_ttml = config_file['outputFile_ttml']

outputFile_text = config_file['localPath'] + config_file['outputFile_text']
outputKey_text = config_file['outputFile_text']



def upload_media_to_s3():
    pprint('Uploading media to S3 ...')
    s3.upload_file(inputFile, bucketName, inputKey)
    pprint('Media was uploaded to s3')

def download_result_from_s3():
    pprint('Downloading result from S3 ...')
    s3.download_file(bucketName, outputKey_json, outputFile_json)
    s3.download_file(bucketName, outputKey_ttml, outputFile_ttml)
    s3.download_file(bucketName, outputKey_text, outputFile_text)
    pprint('Result was downloaded from s3')

def delete_artifacts_from_s3():
    pprint('Deleting s3 artifacts ...')
    s3.delete_object(Bucket=bucketName, Key=inputKey)
    s3.delete_object(Bucket=bucketName, Key=outputKey_json)
    s3.delete_object(Bucket=bucketName, Key=outputKey_ttml)
    s3.delete_object(Bucket=bucketName, Key=outputKey_text)
    pprint('S3 artifacts were deleted')

def get_signed_url_input():
    return s3.generate_presigned_url(
        ClientMethod='get_object',
        Params={
            'Bucket': bucketName,
            'Key': inputKey
        },
        ExpiresIn=60*60)

def get_signed_url_output(outputKey):
    return s3.generate_presigned_url(
        ClientMethod='put_object',
        Params={
            'Bucket': bucketName,
            'Key': outputKey
        },
        ExpiresIn=60*60)


def get_access_token() -> Token:
    # create an instance of the API class
    api_instance: AuthApi = cortex_client.AuthApi(cortex_client.ApiClient(mediator_config))
    return api_instance.get_access_token(client, secret)


def create_speech_to_text_job(signed_url_input, signed_url_otput_json, signed_url_otput_ttml, signed_url_otput_text) -> Job:
    input_file: Locator = Locator(bucketName, inputKey, signed_url_input)
    jsonFormat: Locator = Locator(bucketName, outputKey_json, signed_url_otput_json)
    ttmlFormat: Locator = Locator(bucketName, outputKey_ttml, signed_url_otput_ttml)
    textFormat: Locator = Locator(bucketName, outputKey_text, signed_url_otput_text)

    output_location: SpeechToTextOutput = SpeechToTextOutput(jsonFormat, ttmlFormat, None, textFormat)
    job_input: SpeechToTextInput = SpeechToTextInput(input_file, output_location, language=language_code)
    return Job(job_type='AIJob', job_profile='MediaCortexSpeechToText', job_input=job_input)


def create_job_mediator_input(signed_url_input, signed_url_otput_json, signed_url_otput_ttml, signed_url_otput_text) -> JobMediatorInput:
    job: Job = create_speech_to_text_job(signed_url_input, signed_url_otput_json, signed_url_otput_ttml, signed_url_otput_text)
    return JobMediatorInput(project_service_id=project_service_id, quantity=30, job=job)


def submit_job(job_mediator_input) -> MediatorJob:
    # create an instance of the API class
    api_instance: JobsApi = cortex_client.JobsApi(cortex_client.ApiClient(mediator_config))
    return api_instance.create_job(job_mediator_input)


def get_mediator_job(job_id) -> MediatorJob:
    # create an instance of the API class
    api_instance: JobsApi = cortex_client.JobsApi(cortex_client.ApiClient(mediator_config))
    return api_instance.get_job_by_id(job_id)


def wait_for_complete(mediator_job):
    mediator_status: JobMediatorStatus = mediator_job.status
    while mediator_status.status not in ["COMPLETED", "FAILED"]:
        time.sleep(30)
        mediator_job = get_mediator_job(mediator_job.id)
        mediator_status = mediator_job.status
        pprint(mediator_job)

    if mediator_status.status == "FAILED":
        raise Exception(mediator_status.status_message)

    return mediator_job


def main():
    try:
        # """
        # Upload to S3
        upload_media_to_s3()
        
        # Get signed urls
        pprint('Receiving signed urls ...')
        input_url = get_signed_url_input()
        output_url_json = get_signed_url_output(outputKey_json)
        output_url_ttml = get_signed_url_output(outputKey_ttml)
        output_url_text = get_signed_url_output(outputKey_text)

        pprint('input_url:')
        pprint(input_url)
        pprint('output_url json:')
        pprint(output_url_json)
        pprint('output_url ttml:')
        pprint(output_url_ttml)
        pprint('output_url text:')
        pprint(output_url_text)

        # Get access token for this client.
        pprint('Retreiving access tokens ...')
        token = get_access_token()
        pprint(token.authorization)
        

        # Update api_key with access token information for next API calls
        mediator_config.api_key['tokenSignature'] = token.authorization
        
        

        # Create sample job mediator input structure.
        job_mediator_input = create_job_mediator_input(input_url, output_url_json, output_url_ttml, output_url_text)
        pprint(job_mediator_input)

        # Submit the input job to Mediator
        pprint('Submitting job ...')
        mediator_job = submit_job(job_mediator_input)
        pprint(job_mediator_input)

        # Wait till job is done and get job result
        mediator_job = wait_for_complete(mediator_job)
        pprint(job_mediator_input)

        # Download result
        download_result_from_s3()

        # Delete artifacts
        delete_artifacts_from_s3()
        # """
    except ApiException as e:
        print("Exception when calling api: %s\n" % e)


main()
