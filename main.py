import yaml
import sys
import os
import json
import requests
from datetime import datetime
from helpers.helper import ZAPHelper
from argparse import ArgumentParser

DEFAULT_API_URL = 'https://app.soos.io'


def console_log(message):
    time_now = datetime.utcnow().isoformat(timespec="seconds", sep=" ")
    print(time_now + " SOOS: " + str(message))


def print_line_separator():
    print('----------------------------------------------------------------------------------------------------------')


def exit_app(e):
    console_log('ERROR: ' + str(e))
    sys.exit(1)


def valid_required(key, value):
    if value is None or len(value) == 0:
        exit_app(key + ' is required')


def has_value(prop):
    return prop is not None and len(prop) > 0


def is_true(prop):
    return prop is True


class DASTAnalysisResponse:
    def __init__(self, dast_analysis_api_response):
        self.report_url = dast_analysis_api_response['reportUrl']
        self.analysis_id = dast_analysis_api_response['analysisId']
        self.project_id = dast_analysis_api_response['projectId']


class SOOSDASTAnalysis:
    REPORT_SCAN_RESULT_FILENAME = 'report.json'
    REPORT_SCAN_RESULT_FILE = 'wrk/' + REPORT_SCAN_RESULT_FILENAME
    PY_CMD = 'python3'
    BASE_LINE_SCRIPT = 'zap-baseline.py'
    FULL_SCAN_SCRIPT = 'zap-full-scan.py'
    API_SCAN_SCRIPT = 'zap-api-scan.py'
    CONFIG_FILE_FOLDER = '/zap/config/'
    DEFAULT_CONFIG_FILE = 'config.yml'
    ZAP_TARGET_URL_OPTION = '-t'
    ZAP_RULES_FILE_OPTION = '-c'
    ZAP_CONTEXT_FILE_OPTION = '-n'
    ZAP_MINUTES_DELAY_OPTION = '-m'
    ZAP_DEBUG_OPTION = '-d'
    ZAP_AJAX_SPIDER_OPTION = '-j'
    ZAP_FORMAT_OPTION = '-f'
    ZAP_JSON_REPORT_OPTION = '-J'
    URI_TEMPLATE = '{soos_base_uri}clients/{soos_client_id}/analysis/{soos_analysis_tool}'

    def __init__(self):
        self.client_id = None
        self.api_key = None
        self.project_name = None
        self.base_uri = None
        self.scan_mode = None
        self.fail_on_error = None
        self.target_url = None
        self.rules_file = None
        self.context_file = None
        self.user_context = None
        self.api_scan_format = None
        self.debug_mode = False
        self.ajax_spider_scan = False
        self.spider = False
        self.minutes_delay = None

        # Special Context - loads from script arguments only
        self.commit_hash = None
        self.branch_name = None
        self.branch_uri = None
        self.build_version = None
        self.build_uri = None
        self.operating_environment = None
        self.integration_name = None

        # INTENTIONALLY HARDCODED
        self.integration_type = "CI"
        self.analysis_tool = 'zap'

    def parse_configuration(self, configuration, target_url):
        console_log('Configuration: ' + str(configuration))
        valid_required('Target URL', target_url)
        self.target_url = target_url

        for key, value in configuration.items():
            if key == 'clientId':
                if value is None:
                    try:
                        self.api_key = os.environ.get('SOOS_CLIENT_ID')
                        valid_required(key, self.api_key)
                    except Exception as e:
                        exit_app(e)
                else:
                    valid_required(key, value)
                    self.client_id = value
            elif key == 'apiKey':
                if value is None:
                    try:
                        self.api_key = os.environ.get('SOOS_API_KEY')
                        valid_required(key, self.api_key)
                    except Exception as e:
                        exit_app(e)
                else:
                    valid_required(key, value)
                    self.api_key = value
            elif key == 'apiURL':
                if value is None:
                    self.base_uri = DEFAULT_API_URL
                else:
                    self.base_uri = value
            elif key == 'projectName':
                valid_required(key, value)
                self.project_name = value
            elif key == 'scanMode':
                valid_required(key, value)
                self.scan_mode = value
            elif key == 'failOnError':
                valid_required(key, value)
                self.fail_on_error = value
            elif key == 'rules':
                self.rules_file = value
            elif key == 'debug':
                self.debug_mode = value
            elif key == 'ajaxSpider':
                self.ajax_spider_scan = value
            elif key == 'context':
                self.context_file = value['file']
                self.user_context = value['user']
            elif key == 'contextFile':
                self.context_file = value
            elif key == 'contextUser':
                self.user_context = value
            elif key == 'fullScan':
                self.minutes_delay = value['minutes']
            elif key == 'fullScanMinutes':
                self.minutes_delay = value
            elif key == 'apiScan':
                self.api_scan_format = value['format']
            elif key == 'apiScanFormat':
                self.api_scan_format = value
            elif key == 'commitHash':
                self.commit_hash = value
            elif key == 'branchName':
                self.branch_name = value
            elif key == 'buildVersion':
                self.build_version = value
            elif key == 'branchURI':
                self.branch_uri = value
            elif key == 'buildURI':
                self.build_uri = value
            elif key == 'operatingEnvironment':
                self.operating_environment = value
            elif key == 'integrationName':
                self.integration_name = value

    def __add_target_url_option__(self, args):
        if has_value(self.target_url):
            args.append(self.ZAP_TARGET_URL_OPTION)
            args.append(self.target_url)
        else:
            exit_app('Target url is required.')

    def __add_rules_file_option__(self, args):
        if has_value(self.rules_file):
            args.append(self.ZAP_RULES_FILE_OPTION)
            args.append(self.rules_file)

    def __add_context_file_option__(self, args):
        if has_value(self.context_file):
            args.append(self.ZAP_CONTEXT_FILE_OPTION)
            args.append(self.context_file)

    def __add_debug_option__(self, args):
        if is_true(self.debug_mode):
            args.append(self.ZAP_DEBUG_OPTION)

    def __add_ajax_spider_scan_option__(self, args):
        if is_true(self.ajax_spider_scan):
            args.append(self.ZAP_AJAX_SPIDER_OPTION)

    def __add_minutes_delay_option__(self, args):
        if has_value(self.minutes_delay):
            args.append(self.ZAP_MINUTES_DELAY_OPTION)
            args.append(self.minutes_delay)

    def __add_format_option__(self, args):
        if has_value(self.api_scan_format):
            args.append(self.ZAP_FORMAT_OPTION)
            args.append(self.api_scan_format)
        elif self.scan_mode == 'fullscan':
            exit_app('Format is required for fullscan mode.')

    def __add_report_file__(self, args):
        args.append(self.ZAP_JSON_REPORT_OPTION)
        args.append(self.REPORT_SCAN_RESULT_FILENAME)

    def __generate_command__(self, args):
        self.__add_debug_option__(args)
        self.__add_rules_file_option__(args)
        self.__add_context_file_option__(args)
        self.__add_ajax_spider_scan_option__(args)
        self.__add_minutes_delay_option__(args)

        self.__add_report_file__(args)

        return ' '.join(args)

    def baseline_scan(self):
        args = [self.PY_CMD,
                self.BASE_LINE_SCRIPT]

        self.__add_target_url_option__(args)

        return self.__generate_command__(args)

    def full_scan(self):
        args = [self.PY_CMD,
                self.BASE_LINE_SCRIPT]

        self.__add_target_url_option__(args)

        return self.__generate_command__(args)

    def api_scan(self):
        valid_required('api_scan_format', self.api_scan_format)
        args = [self.PY_CMD,
                self.API_SCAN_SCRIPT]

        self.__add_target_url_option__(args)
        self.__add_format_option__(args)

        return self.__generate_command__(args)

    def active_scan(self):
        """
        Run an Active Scan against a URL.

        The URL to be scanned must be in ZAP's site tree, i.e. it should have already
        been opened using the open-url command or found by running the spider command.
        """

        zap = ZAPHelper()
        options = dict(recursive=True,
                       ajax_spider=self.ajax_spider_scan,
                       spider=True,
                       context=self.context_file,
                       user=self.user_context)

        console_log('Ajax Spider: ' + str(self.ajax_spider_scan))

        zap.scan(target_url=self.target_url, options=options)

    def passive_scan(self):
        valid_required('api_scan_format', self.api_scan_format)
        args = [self.PY_CMD,
                self.API_SCAN_SCRIPT]

        self.__add_target_url_option__(args)
        self.__add_format_option__(args)

        return self.__generate_command__(args)

    def parse_zap_results_file(self):
        with open(self.REPORT_SCAN_RESULT_FILE, mode='r') as file:
            results = file.read()
            zap_report_results = json.loads(results)

        return zap_report_results

    def __generate_api_request__(self):
        url = self.URI_TEMPLATE
        url = url.replace("{soos_base_uri}", self.base_uri)
        url = url.replace("{soos_client_id}", self.client_id)
        url = url.replace("{soos_analysis_tool}", self.analysis_tool)

        return url

    def __make_soos_request__(self, zap_report_results):
        console_log('Making request to SOOS')
        api_url = self.__generate_api_request__()
        console_log('SOOS URL Endpoint: ' + api_url)

        param_values = dict(commitHast=self.commit_hash,
                            branch=self.branch_name,
                            buildVersion=self.build_version,
                            buildUri=self.build_uri,
                            branchUri=self.branch_uri,
                            operationEnvironment=self.operating_environment,
                            integrationName=self.integration_name,
                            result=zap_report_results)

        # Clean up None values
        request_body = {k: v for k, v in param_values.items() if v is not None}

        api_response = requests.post(
            url=api_url,
            data=json.dumps(request_body),
            headers={'x-soos-apikey': self.api_key, 'Content-Type': 'application/json'})

        if api_response.status_code >= 400:
            error_response = api_response.json()
            message = error_response['message']

            exit_app(message)

        elif api_response.status_code == 201:
            return DASTAnalysisResponse(api_response.json())

    def publish_results_to_soos(self):
        try:
            console_log('Starting report results processing')
            zap_report_results = self.parse_zap_results_file()

            results = self.__make_soos_request__(zap_report_results)

            console_log('Report processed successfully')
            print_line_separator()
            console_log('Project Id: ' + results['project_id'])
            console_log('Analysis Id: ' + results['analysis_id'])
            console_log('Report URL: ' + results['report_url'])
            print_line_separator()
            console_log('SOOS DAST Analysis successful')
            print_line_separator()
            sys.exit(0)

        except Exception as e:
            exit_app(e)

    def parse_args(self):
        parser = ArgumentParser()
        parser.add_argument('targetURL',
                            help='The URL to be analyzed by the tool',)
        parser.add_argument('--configFile', help='A Yaml file with all the analysis scan configuration', required=False)
        parser.add_argument('--clientId', help='SOOS Client Id', required=False)
        parser.add_argument('--apiKey', help='SOOS API Key', required=False)
        parser.add_argument('--projectName', help='Project Name to be displayed in the SOOS Application', required=False)
        parser.add_argument('--scanMode',
                            help='DAST Scan mode. Values availables: baseline, fullscan, apiscan, and activescan',
                            default='baseline',
                            required=False)
        parser.add_argument('--apiURL',
                            help='The SOOS API URL',
                            default='https://app.soos.io/api/',
                            required=False)
        parser.add_argument('--debug',
                            help='Enable console log debugging',
                            default=False,
                            type=bool,
                            required=False)
        parser.add_argument('--ajaxSpider',
                            help='Enable Ajax Spider scanning - Useful for Modern Web Apps',
                            type=bool,
                            required=False)
        parser.add_argument('--rules',
                            help='Project Name to be displayed in the SOOS Application',
                            required=False)
        parser.add_argument('--contextFile',
                            help='Project Name to be displayed in the SOOS Application',
                            required=False)
        parser.add_argument('--contextUser',
                            help='Project Name to be displayed in the SOOS Application',
                            required=False)
        parser.add_argument('--fullScanMinutes',
                            help='Project Name to be displayed in the SOOS Application',
                            required=False)
        parser.add_argument('--apiScanFormat',
                            help='Project Name to be displayed in the SOOS Application',
                            required=False)
        parser.add_argument('--activeScanLevel',
                            help='Project Name to be displayed in the SOOS Application',
                            required=False)

        args = parser.parse_args()
        if args.configFile is not None:
            console_log('Reading config file: ' + args.configFile)
            with open(self.CONFIG_FILE_FOLDER+args.configFile, mode='r') as file:
                # The FullLoader parameter handles the conversion from YAML
                # scalar values to Python the dictionary format
                configuration = yaml.load(file, Loader=yaml.FullLoader)
                self.parse_configuration(configuration['config'], args.targetURL)
        else:
            self.parse_configuration(args, args.targetURL)

    def run_analysis(self, configuration_file):
        console_log('Starting SOOS DAST Analysis')
        print_line_separator()

        self.parse_args()

        console_log('Configuration read')
        print_line_separator()

        console_log('Project Name: ' + self.project_name)
        console_log('Scan Mode: ' + self.scan_mode)
        console_log('API URL: ' + self.base_uri)
        console_log('Target URL: ' + self.target_url)
        print_line_separator()

        console_log('Executing ' + self.scan_mode + ' scan')
        # execute test
        command = ''
        if self.scan_mode == 'baseline':
            command = self.baseline_scan()
        elif self.scan_mode == 'fullscan':
            command = self.full_scan()
        elif self.scan_mode == 'apiscan':
            command = self.api_scan()
        elif self.scan_mode == 'activescan':
            self.active_scan()
            sys.exit(0)

        if len(command) == 0:
            exit_app('Invalid scan mode')
            print_line_separator()

        console_log('Command to be executed: ' + command)
        os.system(command)
        print_line_separator()

        self.publish_results_to_soos()


if __name__ == "__main__":
    dastAnalysis = SOOSDASTAnalysis()
    if len(sys.argv) == 2:
        dastAnalysis.run_analysis(sys.argv[1])
    else:
        dastAnalysis.run_analysis(None)
