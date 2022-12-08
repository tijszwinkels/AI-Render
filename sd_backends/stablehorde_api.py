import bpy
import base64
import time
import requests

from .. import (
    config,
    operators,
    utils,
)

API_REQUEST_URL = config.STABLE_HORDE_API_URL_BASE + "/generate/async"
API_CHECK_URL = config.STABLE_HORDE_API_URL_BASE + "/generate/check"
API_GET_URL = config.STABLE_HORDE_API_URL_BASE + "/generate/status"

# CORE FUNCTIONS:

def send_to_api(params, img_file, filename_prefix, sd_model):

    # map the generic params to the specific ones for the Stable Horde API
    stablehorde_params = map_params(params)

    # add a base 64 encoded image to the params
    stablehorde_params["source_image"] = base64.b64encode(img_file.read()).decode()

    # close the image file
    img_file.close()

    # if no api-key specified, use the default non-authenticated api-key
    apikey = utils.get_stable_horde_api_key() if not utils.get_stable_horde_api_key().strip() == "" else "0000000000"

    # create the headers
    headers = {
        "User-Agent": "Blender/" + bpy.app.version_string,
        "Accept": "*/*",
        "Accept-Encoding": "gzip, deflate, br",
        "apikey": apikey
    }

    # send the API request
    start_time = time.monotonic()
    try:
        print(f"Sending request to Stable Horde API: {API_REQUEST_URL}")
        response = requests.post(API_REQUEST_URL, json=stablehorde_params, headers=headers, timeout=20)
        print(response.json())
        id = response.json()["id"]
        img_file.close()
    except requests.exceptions.ReadTimeout:
        img_file.close()
        return operators.handle_error(f"There was an error sending this request to Stable Horde. Please try again in a moment.", "timeout")
    except Exception as e:
        img_file.close()
        return operators.handle_error(f"Error with Stable Horde. Full error message: {e}", "unknown_error")

    # Check the status of the request (For at most request_timeout seconds)
    for i in range(request_timeout()):
        try:
            time.sleep(1)
            URL=API_CHECK_URL + "/" + id
            print(f"Checking status of request at Stable Horde API: {URL}")
            response = requests.get(URL, headers=headers, timeout=20)
            print(f"Waiting for {str(time.monotonic() - start_time)}s. Response: {response.json()}")
            if response.json()["done"] == True:
                print("The horde took " + str(time.monotonic() - start_time) + "s to imagine this frame.")
                break
        except requests.exceptions.ReadTimeout:
            # Ignore timeouts
            print("WARN: Timeout while checking status")
        except Exception as e: # Catch all other errors
            return operators.handle_error(f"Error while checking status: {e}", "unknown_error")
    if (i == request_timeout() - 1):
        return operators.handle_error(f"Timeout generating image. Try again in a moment, or get help. [Get help with timeouts]({config.HELP_WITH_TIMEOUTS_URL})", "timeout")

    # Get the image
    try:
        URL=API_GET_URL + "/" + id
        print(f"Retrieving image from Stable Horde API: {URL}")
        response = requests.get(URL, headers=headers, timeout=20)
        # handle the response
        if response.status_code == 200:
            return handle_api_success(response, filename_prefix)
        else:
            return handle_api_error(response)

    except requests.exceptions.ReadTimeout:
        return operators.handle_error(f"Timeout getting image from Stable Horde. Try again in a moment, or get help. [Get help with timeouts]({config.HELP_WITH_TIMEOUTS_URL})", "timeout")
    except Exception as e:
        return operators.handle_error(f"Error with Stable Horde. Full error message: {e}", "unknown_error")



def handle_api_success(response, filename_prefix):

    # ensure we have the type of response we are expecting
    try:
        response_obj = response.json()
        base64_img = response_obj["generations"][0]["img"]
        print(f"Worker: {response_obj['generations'][0]['worker_name']}, " +
              f"kudos: {response_obj['kudos']}")
    except:
        print("Stable Horde response content: ")
        print(response.content)
        return operators.handle_error("Received an unexpected response from the Stable Horde server.", "unexpected_response")

    # create a temp file
    try:
        output_file = utils.create_temp_file(filename_prefix + "-", suffix=f".{get_image_format().lower()}")
    except:
        return operators.handle_error("Couldn't create a temp file to save image.", "temp_file")

    # decode base64 image
    try:
        img_binary = base64.b64decode(base64_img.replace("data:image/png;base64,", ""))
    except:
        return operators.handle_error("Couldn't decode base64 image from the Stable Horde server.", "base64_decode")

    # save the image to the temp file
    try:
        with open(output_file, 'wb') as file:
            file.write(img_binary)
    except:
        return operators.handle_error("Couldn't write to temp file.", "temp_file_write")

    # return the temp file
    return output_file


def handle_api_error(response):
    return operators.handle_error("The Stable Horde server returned an error: " + str(response.content), "unknown_error")


# PRIVATE SUPPORT FUNCTIONS:

def map_params(params):
    return {
        "prompt": params["prompt"],
        "params": {
            "cfg_scale": params["cfg_scale"],
            "width": params["width"],
            "height": params["height"],
            "denoising_strength": round(1 - params["image_similarity"], 2),
            "seed": str(params["seed"]),
            "steps": params["steps"],
            "sampler_name": params["sampler"],
        }
    }


# PUBLIC SUPPORT FUNCTIONS:

def get_samplers():
    # NOTE: Keep the number values (fourth item in the tuples) in sync with DreamStudio's
    # values (in stability_api.py). These act like an internal unique ID for Blender
    # to use when switching between the lists.
    return [
        ('k_euler', 'Euler', '', 10),
        ('k_euler_a', 'Euler a', '', 20),
        ('k_heun', 'Heun', '', 30),
        ('k_dpm_2', 'DPM2', '', 40),
        ('k_dpm_2_a', 'DPM2 a', '', 50),
        ('k_lms', 'LMS', '', 60),
        # TODO: Stable horde does have karras support, but it's a separate boolean
    ]


def default_sampler():
    return 'k_euler_a'


def request_timeout():
    return 300


def get_image_format():
    return 'WEBP'


def supports_negative_prompts():
    return False


def supports_choosing_model():
    return False


def max_image_size():
    return 1024 * 1024
