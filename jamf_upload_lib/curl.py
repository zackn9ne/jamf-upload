#!/usr/bin/env python3

import json
import os
import subprocess
import uuid
from shutil import rmtree
from collections import namedtuple

def token_based(method, url, data, verbosity=0):
    curl_cmd = [
        "/usr/bin/curl",
        "-X",
        method,
        "-H",
        "Content-type: application/json",
        "--data",
        json.dumps(data),
        url,
    ]
    if verbosity > 0:
        curl_cmd.append("-v")
        print(curl_cmd)
    subprocess.check_output(curl_cmd)
    
    
def request(method, url, auth, verbosity, data="", additional_headers=""):
    """
    build a curl command based on method (GET, PUT, POST, DELETE)
    If the URL contains 'uapi' then token should be passed to the auth variable,
    otherwise the enc_creds variable should be passed to the auth variable
    """
    tmp_dir = make_tmp_dir()
    headers_file = os.path.join(tmp_dir, "curl_headers_from_jamf_upload.txt")
    output_file = os.path.join(tmp_dir, "curl_output_from_jamf_upload.txt")
    cookie_jar = os.path.join(tmp_dir, "curl_cookies_from_jamf_upload.txt")

    # build the curl command
    curl_cmd = [
        "/usr/bin/curl",
        "-X",
        method,
        "-D",
        headers_file,
        "--output",
        output_file,
        url,
    ]

    # the authorisation is Basic unless we are using the uapi and already have a token
    if "uapi" in url and "tokens" not in url:
        curl_cmd.extend(["--header", "authorization: Bearer {}".format(auth)])
    else:
        curl_cmd.extend(["--header", "authorization: Basic {}".format(auth)])

    # set either Accept or Content-Type depending on method
    if method == "GET" or method == "DELETE":
        curl_cmd.extend(["--header", "Accept: application/json"])
    # icon upload requires special method
    elif method == "POST" and "fileuploads" in url:
        curl_cmd.extend(["--header", "Content-type: multipart/form-data"])
        curl_cmd.extend(["--form", f"name=@{data}"])
    elif method == "POST" or method == "PUT":
        if data:
            curl_cmd.extend(["--upload-file", data])
        # uapi sends json, classic API must send xml
        if "uapi" in url:
            curl_cmd.extend(["--header", "Content-type: application/json"])
        else:
            curl_cmd.extend(["--header", "Content-type: application/xml"])
    else:
        print("WARNING: HTTP method {} not supported".format(method))

    # write session
    try:
        with open(headers_file, "r") as file:
            headers = file.readlines()
        existing_headers = [x.strip() for x in headers]
        for header in existing_headers:
            if "APBALANCEID" in header:
                with open(cookie_jar, "w") as fp:
                    fp.write(header)
    except IOError:
        pass

    # look for existing session
    try:
        with open(cookie_jar, "r") as file:
            headers = file.readlines()
        existing_headers = [x.strip() for x in headers]
        for header in existing_headers:
            if "APBALANCEID" in header:
                cookie = header.split()[1].rstrip(";")
                if verbosity > 0:
                    print("Existing cookie found: {}".format(cookie))
                curl_cmd.extend(["--cookie", cookie])

    except IOError:
        print("No existing cookie found - starting new session")

    # additional headers for advanced requests
    if additional_headers:
        curl_cmd.extend(additional_headers)

    # add or remove verbose mode
    if verbosity < 1:
        curl_cmd.append("-s")
    elif verbosity > 1:
        curl_cmd.append("-v")

    if verbosity:
        print("\ncurl command:\n{}".format(" ".join(curl_cmd)))

    # now subprocess the curl command and build the r tuple which contains the
    # headers, status code and outputted data
    subprocess.check_output(curl_cmd)

    r = namedtuple("r", ["headers", "status_code", "output"])
    try:
        with open(headers_file, "r") as file:
            headers = file.readlines()
        r.headers = [x.strip() for x in headers]
        for header in r.headers:
            if "HTTP/1.1" in header and "Continue" not in header:
                r.status_code = int(header.split()[1])
        with open(output_file, "rb") as file:
            if "uapi" in url:
                r.output = json.load(file)
            else:
                r.output = file.read()
        return r
    except IOError:
        print("WARNING: {} not found".format(headers_file))


def status_check(r, endpoint_type, obj_name, request_type="upload"):
    """Return a message dependent on the HTTP response"""

    if r.status_code == 200 or r.status_code == 201:
        print(
            "{} '{}' {} was successful".format(
                endpoint_type, obj_name, request_type.lower()
            )
        )
        return "break"
    elif r.status_code == 409:
        print(
            "WARNING: {} {} failed due to a conflict".format(
                endpoint_type, request_type.lower()
            )
        )
        return "break"
    elif r.status_code == 401:
        print(
            "ERROR: {} {} failed due to permissions error".format(
                endpoint_type, request_type.lower()
            )
        )
        return "break"


def write_json_file(data, tmp_dir="/tmp/jamf_upload"):
    """dump some json to a temporary file"""
    make_tmp_dir(tmp_dir)
    tf = os.path.join(tmp_dir, f"jamf_upload_{str(uuid.uuid4())}.json")
    with open(tf, "w") as fp:
        json.dump(data, fp)
    return tf


def write_temp_file(data, tmp_dir="/tmp/jamf_upload"):
    """dump some text to a temporary file"""
    make_tmp_dir(tmp_dir)
    tf = os.path.join(tmp_dir, f"jamf_upload_{str(uuid.uuid4())}.txt")
    with open(tf, "w") as fp:
        fp.write(data)
    return tf


def make_tmp_dir(tmp_dir="/tmp/jamf_upload"):
    """make the tmp directory"""
    if not os.path.exists(tmp_dir):
        os.mkdir(tmp_dir)
    return tmp_dir


def clear_tmp_dir(tmp_dir="/tmp/jamf_upload"):
    """remove the tmp directory"""
    if os.path.exists(tmp_dir):
        rmtree(tmp_dir)
    return tmp_dir
