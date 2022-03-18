import base64
import gzip
import json
import os
import sys
from argparse import ArgumentParser, Namespace
from datetime import datetime
from typing import List, Optional, Any, Dict, NoReturn

import requests
import yaml
from requests import Response, put, post, patch

import helpers.constants as Constants
from helpers.utils import log, valid_required, has_value, exit_app, is_true, print_line_separator, \
    check_site_is_available, log_error, unescape_string, read_file, convert_string_to_b64, generate_header, \
    handle_response, ErrorAPIResponse, raise_max_retry_exception
from model.log_level import LogLevel

SCRIPT_VERSION = "alpha"

param_mapper = {}


class DASTStartAnalysisResponse:
    def __init__(self, dast_analysis_api_response):
        self.analysis_id = dast_analysis_api_response[
            "analysisId"] if "analysisId" in dast_analysis_api_response else None
        self.branch_hash = dast_analysis_api_response[
            "branchHash"] if "branchHash" in dast_analysis_api_response else None
        self.scan_type = dast_analysis_api_response["scanType"] if "scanType" in dast_analysis_api_response else None
        self.scan_url = dast_analysis_api_response["scanUrl"] if "scanUrl" in dast_analysis_api_response else None
        self.scan_status_url = dast_analysis_api_response[
            "scanStatusUrl"] if "scanStatusUrl" in dast_analysis_api_response else None
        self.errors = dast_analysis_api_response["errors"] if "errors" in dast_analysis_api_response else None
        self.project_id = dast_analysis_api_response["projectId"] if "projectId" in dast_analysis_api_response else None
        if self.project_id is None:
            self.project_id = dast_analysis_api_response[
                "projectHash"] if "projectHash" in dast_analysis_api_response else None


class SOOSDASTAnalysis:

    def __init__(self):
        self.client_id: Optional[str] = None
        self.api_key: Optional[str] = None
        self.project_name: Optional[str] = None
        self.base_uri: Optional[str] = None
        self.scan_mode: Optional[str] = None
        self.fail_on_error: Optional[str] = None
        self.target_url: Optional[str] = None
        self.rules_file: Optional[str] = None
        self.context_file: Optional[str] = None
        self.user_context: Optional[str] = None
        self.api_scan_format: Optional[str] = None
        self.debug_mode: bool = False
        self.ajax_spider_scan: bool = False
        self.spider: bool = False
        self.minutes_delay: Optional[str] = None

        # Special Context - loads from script arguments only
        self.commit_hash: Optional[str] = None
        self.branch_name: Optional[str] = None
        self.branch_uri: Optional[str] = None
        self.build_version: Optional[str] = None
        self.build_uri: Optional[str] = None
        self.operating_environment: Optional[str] = None
        self.log_level: Optional[str] = None
        self.zap_options: Optional[str] = None
        self.request_cookies: Optional[str] = None
        self.request_header: Optional[str] = None
        self.integration_name: str = Constants.DEFAULT_INTEGRATION_NAME

        # INTENTIONALLY HARDCODED
        self.integration_type: str = Constants.DEFAULT_INTEGRATION_TYPE
        self.dast_analysis_tool: str = Constants.DEFAULT_DAST_TOOL

        # Auth Options
        self.auth_auto: Optional[str] = '0'
        self.auth_loginUrl: Optional[str] = None
        self.auth_username: Optional[str] = Constants.EMPTY_STRING
        self.auth_password: Optional[str] = Constants.EMPTY_STRING
        self.auth_username_field_name: Optional[str] = Constants.EMPTY_STRING
        self.auth_password_field_name: Optional[str] = Constants.EMPTY_STRING
        self.auth_submit_field_name: Optional[str] = Constants.EMPTY_STRING
        self.auth_first_submit_field_name: Optional[str] = Constants.EMPTY_STRING
        self.auth_excludeUrls: Optional[str] = Constants.EMPTY_STRING
        self.auth_display: bool = False

        self.generate_sarif_report: bool = False
        self.github_pat: Optional[str] = None

        self.scan_mode_map: Dict = {
            Constants.BASELINE: self.baseline_scan,
            Constants.FULL_SCAN: self.full_scan,
            Constants.API_SCAN: self.api_scan
        }

    def parse_configuration(self, configuration: Dict, target_url: str):
        valid_required("Target URL", target_url)
        self.target_url = target_url
        log(f"Configuration", log_level=LogLevel.DEBUG)
        for key, value in configuration.items():
            log(f"{key}={value}", log_level=LogLevel.DEBUG)
            if key == "clientId":
                if value is None:
                    try:
                        self.client_id = os.environ.get(Constants.SOOS_CLIENT_ID_KEY)
                        valid_required(key, self.client_id)
                    except Exception as e:
                        exit_app(e)
                else:
                    valid_required(key, value)
                    self.client_id = value
            elif key == "apiKey":
                if value is None:
                    try:
                        self.api_key = os.environ.get(Constants.SOOS_API_KEY)
                        valid_required(key, self.api_key)
                    except Exception as e:
                        exit_app(e)
                else:
                    valid_required(key, value)
                    self.api_key = value
            elif key == "apiURL":
                if value is None:
                    self.base_uri = Constants.DEFAULT_API_URL
                else:
                    self.base_uri = value
            elif key == "projectName":
                valid_required(key, value)
                self.project_name = unescape_string(value)
            elif key == "scanMode":
                valid_required(key, value)
                self.scan_mode = value
            elif key == "failOnError":
                valid_required(key, value)
                self.fail_on_error = value
            elif key == "rules":
                self.rules_file = value
            elif key == "debug":
                self.debug_mode = True
            elif key == "ajaxSpider":
                self.ajax_spider_scan = True
            elif key == "context":
                self.context_file = value["file"]
                self.user_context = value["user"]
            elif key == "contextFile":
                self.context_file = value
            elif key == "contextUser":
                self.user_context = value
            elif key == "fullScan":
                self.minutes_delay = value["minutes"]
            elif key == "fullScanMinutes":
                self.minutes_delay = value
            elif key == "apiScan":
                self.api_scan_format = value["format"]
            elif key == "apiScanFormat":
                self.api_scan_format = value
            elif key == "commitHash":
                self.commit_hash = value
            elif key == "branchName":
                self.branch_name = value
            elif key == "buildVersion":
                self.build_version = value
            elif key == "branchURI":
                self.branch_uri = value
            elif key == "buildURI":
                self.build_uri = value
            elif key == "operatingEnvironment":
                self.operating_environment = value
            elif key == "integrationName":
                self.integration_name = value
            elif key == "integrationType":
                self.integration_type = value
            elif key == 'authAuto':
                self.auth_auto = '1'
            elif key == 'authDisplay':
                self.auth_display = True
            elif key == 'authUsername':
                self.auth_username = value
            elif key == 'authPassword':
                self.auth_password = value
            elif key == 'authLoginURL':
                self.auth_loginUrl = value
            elif key == 'authUsernameField':
                self.auth_username_field_name = value
            elif key == 'authPasswordField':
                self.auth_password_field_name = value
            elif key == 'authSubmitField':
                self.auth_submit_field_name = value
            elif key == 'authFirstSubmitField':
                self.auth_first_submit_field_name = value
            elif key == "level":
                self.log_level = value
            elif key == "zapOptions":
                self.zap_options = value
            elif key == "requestCookies":
                self.request_cookies = value
            elif key == "requestHeader":
                self.request_header = value
            elif key == "sarif":
                self.generate_sarif_report = value
            elif key == "gpat":
                self.github_pat = value
                log("GITHUB PAT: " + self.github_pat)

    def __add_target_url_option__(self, args: List[str]) -> NoReturn:
        if has_value(self.target_url):
            args.append(Constants.ZAP_TARGET_URL_OPTION)
            args.append(self.target_url)
        else:
            exit_app("Target url is required.")

    def __add_rules_file_option__(self, args: List[str]) -> NoReturn:
        if has_value(self.rules_file):
            args.append(Constants.ZAP_RULES_FILE_OPTION)
            args.append(self.rules_file)

    def __add_context_file_option__(self, args: List[str]) -> NoReturn:
        if has_value(self.context_file):
            args.append(Constants.ZAP_CONTEXT_FILE_OPTION)
            args.append(self.context_file)

    def __add_debug_option__(self, args: List[str]) -> NoReturn:
        if is_true(self.debug_mode):
            args.append(Constants.ZAP_DEBUG_OPTION)

    def __add_ajax_spider_scan_option__(self, args: List[str]) -> NoReturn:
        if is_true(self.ajax_spider_scan):
            args.append(Constants.ZAP_AJAX_SPIDER_OPTION)

    def __add_minutes_delay_option__(self, args: List[str]) -> NoReturn:
        if has_value(self.minutes_delay):
            args.append(Constants.ZAP_MINUTES_DELAY_OPTION)
            args.append(self.minutes_delay)

    def __add_format_option__(self, args: List[str]) -> NoReturn:
        if has_value(self.api_scan_format):
            args.append(Constants.ZAP_FORMAT_OPTION)
            args.append(self.api_scan_format)
        elif self.scan_mode == Constants.API_SCAN:
            exit_app("Format is required for apiscan mode.")

    def __add_log_level_option__(self, args: List[str]) -> NoReturn:
        if has_value(self.log_level):
            args.append(Constants.ZAP_MINIMUM_LEVEL_OPTION)
            args.append(self.log_level)

    def __add_report_file__(self, args: List[str]) -> NoReturn:
        args.append(Constants.ZAP_JSON_REPORT_OPTION)
        args.append(Constants.REPORT_SCAN_RESULT_FILENAME)

    def __add_zap_options__(self, args: List[str]) -> NoReturn:
        log(f"Adding Zap Options")
        args.append(Constants.ZAP_OTHER_OPTIONS)

        zap_options: List[str] = list()
        if self.auth_loginUrl is not None:
            zap_options.append(self.__add_custom_option__(label="auth.loginurl", value=self.auth_loginUrl))
        if self.request_cookies is not None:
            zap_options.append(self.__add_custom_option__(label="request.custom_cookies", value=self.request_cookies))
        if self.request_header is not None:
            zap_options.append(self.__add_custom_option__(label="request.custom_header", value=self.request_header))

        args.append(" ".join(zap_options))

    def __add_custom_option__(self, label, value) -> str:
        return f"{label}=\"{value}\""

    def __add_hook_option__(self, args: List[str]) -> NoReturn:
        args.append(Constants.ZAP_HOOK_OPTION)
        args.append('/zap/hooks/soos_dast_hook.py')

    def __generate_command__(self, args: List[str]) -> str:
        self.__add_debug_option__(args)
        self.__add_rules_file_option__(args)
        self.__add_context_file_option__(args)
        self.__add_ajax_spider_scan_option__(args)
        self.__add_minutes_delay_option__(args)
        log(f"Add ZAP Options?")
        log(f"Auth Login: {str(self.auth_loginUrl)}")
        log(f"Zap Options: {str(self.zap_options)}")
        log(f"Cookies: {str(self.request_cookies)}")
        log(f"Github PAT: {str(self.github_pat)}")
        if self.auth_loginUrl or self.zap_options or self.request_cookies is not None:
            self.__add_zap_options__(args)

        self.__add_hook_option__(args)

        self.__add_report_file__(args)

        return " ".join(args)

    def baseline_scan(self) -> str:
        args: List[str] = [Constants.PY_CMD, Constants.BASE_LINE_SCRIPT]

        self.__add_target_url_option__(args)

        return self.__generate_command__(args)

    def full_scan(self) -> str:
        args: List[str] = [Constants.PY_CMD, Constants.FULL_SCAN_SCRIPT]

        self.__add_target_url_option__(args)

        return self.__generate_command__(args)

    def api_scan(self) -> str:
        valid_required("api_scan_format", self.api_scan_format)
        args: List[str] = [Constants.PY_CMD, Constants.API_SCAN_SCRIPT]

        self.__add_target_url_option__(args)
        self.__add_format_option__(args)

        return self.__generate_command__(args)

    def open_zap_results_file(self):
        return read_file(file_path=Constants.REPORT_SCAN_RESULT_FILE)

    def __generate_start_dast_analysis_url__(self) -> str:
        url = Constants.URI_START_DAST_ANALYSIS_TEMPLATE_v2.format(soos_base_uri=self.base_uri,
                                                                   soos_client_id=self.client_id)

        return url

    def __generate_upload_results_url__(self, project_id: str, branch_hash: str, analysis_id: str) -> str:
        url = Constants.URI_UPLOAD_DAST_RESULTS_TEMPLATE_v2.format(soos_base_uri=self.base_uri,
                                                                   soos_client_id=self.client_id,
                                                                   soos_project_id=project_id,
                                                                   soos_branch_hash=branch_hash,
                                                                   soos_analysis_id=analysis_id)
        return url

    def __generate_project_details_url__(self, project_id: str) -> str:
        url = Constants.URI_PROJECT_DETAILS_TEMPLATE.format(soos_base_uri=self.base_uri,
                                                            soos_project_id=project_id)
        return url

    def __make_soos_start_analysis_request__(self) -> DASTStartAnalysisResponse:
        message: str = "An error has occurred Starting the Analysis"
        try:
            log("Making request to SOOS")
            api_url: str = self.__generate_start_dast_analysis_url__()
            log(f"SOOS URL Endpoint: {api_url}")

            # Validate required fields
            if (
                    self.project_name is None
                    or len(self.project_name) == 0
                    or self.scan_mode is None
                    or len(self.scan_mode) == 0
            ):
                log("projectName and scanMode are required", LogLevel.ERROR)
                sys.exit(1)

            param_values: dict = dict(
                projectName=self.project_name,
                name=datetime.now().strftime("%m/%d/%Y, %H:%M:%S"),
                integrationType=self.integration_type,
                scriptVersion=SCRIPT_VERSION,
                toolName=self.dast_analysis_tool,
                commitHash=self.commit_hash,
                branch=self.branch_name,
                branchUri=self.branch_uri,
                buildVersion=self.build_version,
                buildUri=self.build_uri,
                operationEnvironment=self.operating_environment,
                integrationName=self.integration_name,
            )

            # Clean up None values
            request_body = {k: v for k, v in param_values.items() if v is not None}

            error_response: Optional[Any] = None

            attempt = 0

            data = json.dumps(request_body)

            for attempt in range(0, Constants.MAX_RETRY_COUNT):
                api_response: Response = post(
                    url=api_url,
                    data=data,
                    headers={"x-soos-apikey": self.api_key, "Content-Type": Constants.JSON_HEADER_CONTENT_TYPE}
                )

                if api_response.ok:
                    return DASTStartAnalysisResponse(api_response.json())
                else:
                    log_error(api_response)
                    error_response = api_response
                    log(
                        "An error has occurred performing the request. Retrying Request: "
                        + str(attempt + 1)
                        + "Attempts"
                    )

            if attempt > Constants.MAX_RETRY_COUNT and error_response is not None:
                error_response = error_response.json()
                message = error_response["message"]

        except Exception as e:
            log("ERROR:" + str(e))
            message = message if message is not None else "An error has occurred Starting the Analysis"

        exit_app(message)

    def __make_soos_scan_status_request__(self, project_id: str, branch_hash: str,
                                          analysis_id: str, status: str,
                                          status_message: Optional[str]) -> bool:
        message: str = "An error has occurred Starting the Analysis"
        try:
            log("Making request to SOOS")
            api_url: str = self.__generate_upload_results_url__(project_id, branch_hash, analysis_id)
            log(f"SOOS URL Endpoint: {api_url}")

            param_values: dict = dict(
                status=status,
                message=status_message
            )

            # Clean up None values
            request_body = {k: v for k, v in param_values.items() if v is not None}

            error_response: Optional[Any] = None

            attempt = 0

            data = json.dumps(request_body)

            for attempt in range(0, Constants.MAX_RETRY_COUNT):
                api_response: Response = patch(
                    url=api_url,
                    data=data,
                    headers={"x-soos-apikey": self.api_key, "Content-Type": Constants.JSON_HEADER_CONTENT_TYPE}
                )

                if api_response.ok:
                    return True
                else:
                    log_error(api_response)
                    error_response = api_response
                    log(
                        "An error has occurred performing the request. Retrying Request: "
                        + str(attempt + 1)
                        + "Attempts"
                    )

            if attempt > Constants.MAX_RETRY_COUNT and error_response is not None:
                error_response = error_response.json()
                message = error_response["message"]

        except Exception as e:
            log("ERROR:" + str(e))
            message = message if message is not None else "An error has occurred setting the scan status"
            self.__make_soos_scan_status_request__(project_id=project_id,
                                                   branch_hash=branch_hash,
                                                   analysis_id=analysis_id,
                                                   status="Error",
                                                   status_message=message
                                                   )

        exit_app(message)

    def __make_upload_dast_results_request__(
            self, project_id: str, branch_hash: str, analysis_id: str
    ) -> bool:
        error_response = None
        error_message: Optional[str] = None
        try:
            log("Starting report results processing")
            zap_report = self.open_zap_results_file()
            log("Making request to SOOS")
            api_url: str = self.__generate_upload_results_url__(project_id, branch_hash, analysis_id)
            log("SOOS URL Upload Results Endpoint: " + api_url)
            results_json = json.loads(zap_report)

            zap_report_encoded = convert_string_to_b64(json.dumps(results_json))
            files = {"base64Manifest": zap_report_encoded}

            attempt: int = 1

            while attempt <= Constants.MAX_RETRY_COUNT:
                api_response: Response = put(
                    url=api_url,
                    data=dict(resultVersion=results_json["@version"]),
                    files=files,
                    headers={
                        "x-soos-apikey": self.api_key,
                        "Content_type": Constants.MULTIPART_HEADER_CONTENT_TYPE,
                    },
                )

                if api_response.ok:
                    log("SOOS Upload Success")
                    return True
                else:
                    error_response = api_response
                    log_error(error_response)
                    log(
                        f"An error has occurred performing the request. Retrying Request: {str(attempt)} attempts"
                    )
                    attempt = attempt + 1

            if attempt > Constants.MAX_RETRY_COUNT and error_response is not None:
                error_response = error_response.json()
                error_message = error_response["message"]

        except Exception as e:
            log(str(e))

        self.__make_soos_scan_status_request__(project_id=project_id,
                                               branch_hash=branch_hash,
                                               analysis_id=analysis_id,
                                               status="Error",
                                               status_message=error_message
                                               )
        exit_app(error_message)

    def publish_results_to_soos(self, project_id: str, branch_hash: str, analysis_id: str, report_url: str) -> None:
        try:
            self.__make_upload_dast_results_request__(project_id=project_id, branch_hash=branch_hash,
                                                      analysis_id=analysis_id)

            print_line_separator()
            log("Report processed successfully")
            log(f"Project Id: {project_id}")
            log(f"Branch Hash: {branch_hash}")
            log(f"Analysis Id: {analysis_id}")
            print_line_separator()
            log("SOOS DAST Analysis successful")
            log(f"Project URL: {report_url}")
            print_line_separator()

        except Exception as e:
            self.__make_soos_scan_status_request__(project_id=project_id,
                                                   branch_hash=branch_hash,
                                                   analysis_id=analysis_id,
                                                   status="Error",
                                                   status_message="An Unexpected error has occurred uploading ZAP Report Results"
                                                   )
            exit_app(e)

    def parse_args(self) -> None:
        parser = ArgumentParser(description="SOOS DAST Analysis Script")
        parser.add_argument(
            "targetURL",
            help="target URL including the protocol, eg https://www.example.com",
        )
        parser.add_argument(
            "--configFile",
            help="SOOS yaml file with all the configuration for the DAST Analysis",
            required=False,
        )
        parser.add_argument("--clientId", help="SOOS Client Id", required=False)
        parser.add_argument("--apiKey", help="SOOS API Key", required=False)
        parser.add_argument("--projectName", help="SOOS project name", required=False)
        parser.add_argument(
            "--scanMode",
            help="SOOS DAST scan mode. Values available: baseline, fullscan, apiscan, and activescan",
            default="baseline",
            required=False,
        )
        parser.add_argument(
            "--apiURL",
            help="SOOS API URL",
            default="https://api.soos.io/api/",
            required=False,
        )
        parser.add_argument(
            "--debug",
            help="show debug messages",
            default=False,
            type=bool,
            required=False,
        )
        parser.add_argument(
            "--ajaxSpider",
            help="use the Ajax spider in addition to the traditional one",
            type=bool,
            required=False,
        )
        parser.add_argument(
            "--rules",
            help="rules file to use to INFO, IGNORE or FAIL warnings",
            required=False,
        )
        parser.add_argument(
            "--contextFile",
            help="context file which will be loaded prior to scanning the target",
            required=False,
        )
        parser.add_argument(
            "--contextUser",
            help="username to use for authenticated scans - must be defined in the given context file",
            required=False,
        )
        parser.add_argument(
            "--fullScanMinutes",
            help="Project Name to be displayed in the SOOS Application",
            required=False,
        )
        parser.add_argument(
            "--apiScanFormat",
            help="target API format: openapi, soap, or graphql",
            required=False,
        )
        parser.add_argument(
            "--level",
            help="minimum level to show: PASS, IGNORE, INFO, WARN or FAIL",
            required=False,
        )
        parser.add_argument(
            "--integrationName",
            help="Integration Name (e.g. Provider)",
            required=False,
        )
        parser.add_argument(
            "--authDisplay",
            help="minimum level to show: PASS, IGNORE, INFO, WARN or FAIL",
            required=False,
        )
        parser.add_argument(
            "--authUsername",
            help="Username to use in auth apps",
            required=False,
        )
        parser.add_argument(
            "--authPassword",
            help="Password to use in auth apps",
            required=False,
        )
        parser.add_argument(
            "--authLoginURL",
            help="login url to use in auth apps",
            required=False,
        )
        parser.add_argument(
            "--authUsernameField",
            help="Username input id to use in auth apps",
            required=False,
        )
        parser.add_argument(
            "--authPasswordField",
            help="Password input id to use in auth apps",
            required=False,
        )
        parser.add_argument(
            "--authSubmitField",
            help="Submit button id to use in auth apps",
            required=False,
        )
        parser.add_argument(
            "--authFirstSubmitField",
            help="First submit button id to use in auth apps",
            required=False,
        )
        parser.add_argument(
            "--zapOptions",
            help="ZAP Additional Options",
            required=False,
        )
        parser.add_argument(
            "--requestCookies",
            help="Set Cookie values for the requests to the target URL",
            required=False,
        )
        parser.add_argument(
            "--requestHeader",
            help="Set extra Header requests",
            required=False,
        )
        parser.add_argument(
            "--commitHash",
            help="Set the commit hash value",
            type=str,
            default=None,
            required=False,
        )
        parser.add_argument(
            "--branchName",
            help="Set the branch name",
            type=str,
            default=None,
            required=False,
        )
        parser.add_argument(
            "--branchURI",
            help="Set the branch URI",
            default=None,
            required=False,
        )
        parser.add_argument(
            "--buildVersion",
            help="Set the build version",
            type=str,
            default=None,
            required=False,
        )
        parser.add_argument(
            "--buildURI",
            help="Set the build URI",
            type=str,
            default=None,
            required=False,
        )
        parser.add_argument(
            "--operatingEnvironment",
            help="Set the Operating Environment",
            type=str,
            default=None,
            required=False,
        )

        parser.add_argument("--sarif",
                            help="Upload SARIF Report to GitHub",
                            type=bool,
                            default=False,
                            required=False
                            )

        parser.add_argument("--gpat",
                            help="GitHub Personal Authorization Token",
                            type=str,
                            default=False,
                            required=False
                            )

        args: Namespace = parser.parse_args()
        if args.configFile is not None:
            log(f"Reading config file: {args.configFile}", log_level=LogLevel.DEBUG)
            file = read_file(file_path=Constants.CONFIG_FILE_FOLDER + args.configFile)
            configuration = yaml.load(file, Loader=yaml.FullLoader)
            self.parse_configuration(configuration["config"], args.targetURL)
        else:
            self.parse_configuration(vars(args), args.targetURL)

    def run_analysis(self) -> None:
        try:
            log("Starting SOOS DAST Analysis")
            print_line_separator()

            self.parse_args()

            log("Configuration read")
            print_line_separator()

            log(f"Project Name: {self.project_name}")
            log(f"Scan Mode: {self.scan_mode}")
            log(f"API URL: {self.base_uri}")
            log(f"Target URL: {self.target_url}")
            print_line_separator()

            check: bool = check_site_is_available(self.target_url)

            if check is False:
                exit_app(f"The URL {self.target_url} is not available")
                return None

            log(f"Executing {self.scan_mode} scan")
            soos_dast_start_response = self.__make_soos_start_analysis_request__()
            # execute test
            scan_function = self.scan_mode_map.get(self.scan_mode, None)

            if scan_function is None:
                exit_app(f"The scan mode {self.scan_mode} is invalid.")
                return None

            command: str = scan_function()

            log(f"Command to be executed: {command}")
            self.__make_soos_scan_status_request__(project_id=soos_dast_start_response.project_id,
                                                   branch_hash=soos_dast_start_response.branch_hash,
                                                   analysis_id=soos_dast_start_response.analysis_id,
                                                   status="Running"
                                                   )

            os.system(command)

            run_success = os.path.exists(Constants.REPORT_SCAN_RESULT_FILE)

            print_line_separator()
            if run_success is False:
                self.__make_soos_scan_status_request__(project_id=soos_dast_start_response.project_id,
                                                       branch_hash=soos_dast_start_response.branch_hash,
                                                       analysis_id=soos_dast_start_response.analysis_id,
                                                       status="Error",
                                                       status_message=f"An Unexpected error has occurred running the {self.scan_mode} scan"
                                                       )
                raise Exception(f"An Unexpected error has occurred running the {self.scan_mode} scan")

            self.publish_results_to_soos(
                project_id=soos_dast_start_response.project_id,
                branch_hash=soos_dast_start_response.branch_hash,
                analysis_id=soos_dast_start_response.analysis_id,
                report_url=soos_dast_start_response.scan_url,
            )

            SOOSSARIFReport.exec(analysis=self,
                                 project_hash=soos_dast_start_response.project_id,
                                 branch_hash=soos_dast_start_response.branch_hash,
                                 scan_id=soos_dast_start_response.analysis_id)

            self.__make_soos_scan_status_request__(project_id=soos_dast_start_response.project_id,
                                                   branch_hash=soos_dast_start_response.branch_hash,
                                                   analysis_id=soos_dast_start_response.analysis_id,
                                                   status="Finished",
                                                   )

            sys.exit(0)

        except Exception as e:
            exit_app(e)


class SOOSSARIFReport:
    API_RETRY_COUNT = 3

    URL_TEMPLATE = '{soos_base_uri}clients/{clientHash}/projects/{projectHash}/branches/{branchHash}/scan-types/dast/scans/{scanId}/formats/sarif'
    GITHUB_URL_TEMPLATE = 'https://api.github.com/repos/{project_name}/code-scanning/sarifs'

    errors_dict = {
        400: "Github: The sarif report is invalid",
        403: "Github: The repository is archived or if github advanced security is not enabled for this repository",
        404: "Github: Resource not found",
        413: "Github: The sarif report is too large",
        503: "Github: Service Unavailable"
    }

    def __init__(self):
        pass

    @staticmethod
    def generate_soos_sarif_url(base_uri: str, client_id: str, project_hash: str, branch_hash: str,
                                scan_id: str) -> str:
        return SOOSSARIFReport.URL_TEMPLATE.format(soos_base_uri=base_uri,
                                                   clientHash=client_id,
                                                   projectHash=project_hash,
                                                   branchHash=branch_hash,
                                                   scanId=scan_id)

    @staticmethod
    def generate_github_sarif_url(project_name: str) -> str:
        return SOOSSARIFReport.GITHUB_URL_TEMPLATE.format(project_name=project_name)

    @staticmethod
    def exec(analysis: SOOSDASTAnalysis, project_hash: str, branch_hash: str,
             scan_id: str) -> NoReturn:
        try:
            log("Uploading SARIF Response")
            url = SOOSSARIFReport.generate_soos_sarif_url(base_uri=analysis.base_uri,
                                                          client_id=analysis.client_id,
                                                          project_hash=project_hash,
                                                          branch_hash=branch_hash,
                                                          scan_id=scan_id)

            headers = generate_header(api_key=analysis.api_key, content_type="application/json")
            attempt = 0
            sarif_json_response = None

            for attempt in range(0, SOOSSARIFReport.API_RETRY_COUNT):
                api_response: requests.Response = requests.get(url=url, headers=headers)
                sarif_json_response = handle_response(api_response)
                if type(sarif_json_response) is ErrorAPIResponse:
                    error_message = f"A Generate SARIF Report API Exception Occurred. Attempt {str(attempt + 1)} of {str(SOOSSARIFReport.API_RETRY_COUNT)}"
                    log(f"{error_message}\n{sarif_json_response.code}-{sarif_json_response.message}")
                else:
                    log("SARIF Report")
                    log(str(sarif_json_response))
                    break

            raise_max_retry_exception(attempt=attempt, retry_count=SOOSSARIFReport.API_RETRY_COUNT)

            if sarif_json_response is None:
                raise Exception("An Error has occurred generating SARIF Response")
            else:
                sarif_report_str = json.dumps(sarif_json_response)
                compressed_sarif_response = base64.b64encode(gzip.compress(bytes(sarif_report_str, 'UTF-8')))

                github_body_request = {
                    "commit_sha": analysis.commit_hash,
                    "ref": analysis.branch_name,
                    "sarif": compressed_sarif_response.decode(encoding='UTF-8'),
                }

                github_sarif_url = SOOSSARIFReport.generate_github_sarif_url(project_name=analysis.project_name)
                headers = {"Accept": "application/vnd.github.v3+json", "Authorization": f"token {analysis.github_pat}"}

                sarif_github_response = requests.post(url=github_sarif_url, data=json.dumps(github_body_request),
                                                      headers=headers)

                if sarif_github_response.status_code >= 400:
                    SOOSSARIFReport.handle_github_sarif_error(status=sarif_github_response.status_code,
                                                              json_response=sarif_github_response.json())
                else:
                    sarif_github_json_response = sarif_github_response.json()
                    sarif_url = sarif_github_json_response["url"]
                    sarif_github_status_response = requests.get(url=sarif_url,
                                                                headers=headers)

                    if sarif_github_status_response.status_code >= 400:
                        SOOSSARIFReport.handle_github_sarif_error(status=sarif_github_status_response.status_code,
                                                                  json_response=sarif_github_status_response.json())
                    else:
                        status_json_response = sarif_github_status_response.json()
                        processing_status = status_json_response["processing_status"]
                        log("SARIF Report uploaded to GitHub")
                        log(f"Processing Status: {processing_status}")

        except Exception as sarif_exception:
            log(f"ERROR: {str(sarif_exception)}")

    @staticmethod
    def handle_github_sarif_error(status, json_response):

        error_message = json_response["message"] if json_response is not None and json_response[
            "message"] is not None else SOOSSARIFReport.errors_dict[status]
        if error_message is None:
            error_message = "An unexpected error has occurred uploading the sarif report to GitHub"

        log(f"ERROR: {error_message}")


if __name__ == "__main__":
    dastAnalysis = SOOSDASTAnalysis()
    dastAnalysis.run_analysis()
