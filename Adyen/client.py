#!/bin/python
import json as json_lib
import re

from . import util
from .httpclient import HTTPClient
from .exceptions import (
    AdyenAPICommunicationError,
    AdyenAPIAuthenticationError,
    AdyenAPIInvalidPermission,
    AdyenAPIValidationError,
    AdyenInvalidRequestError,
    AdyenAPIInvalidFormat,
    AdyenAPIInvalidAmount)

import datetime
from datetime import timedelta
import logging
from adyen_log import logname,getlogger
logger = logging.getLogger(logname())


BASE_PAL_url = "https://pal-{}.adyen.com/pal/servlet"
BASE_HPP_url = "https://{}.adyen.com/hpp"
API_VERSION = "v12"
API_CLIENT_ATTR = ["username","password","review_payout_user",
    "review_payout_password","confirm_payout_user","confirm_payout_password",
    "platform","merchant_account","merchant_specific_url","hmac"]

class AdyenResult(object):
    """
    Args:
        message (dict, optional): Parsed message returned from API client.
        status_code (int, optional): Default 200. HTTP response code, ie 200,
            404, 500, etc.
        psp (str, optional): Psp reference returned by Adyen for a payment.
        raw_request (str, optionl): Raw request placed to Adyen.
        raw_response (str, optional): Raw response returned by Adyen.

    """

    def __init__(self,message=None,status_code=200,psp="",raw_request="",raw_response=""):
        self.message = message
        self.status_code = status_code
        self.psp = psp
        self.raw_request=raw_request
        self.raw_response=raw_response
        self.details = {}
    """
    def __setattr__(self, attr, value):
        super(AdyenResult, self).__setattr__(attr, value)

    def __getattr__(self, attr):
        if attr in self.message:
            return self.message[attr]
        else:
            raise AttributeError
    """


    def __str__(self):
        return repr(self.message)

class AdyenClient(object):
    """A requesting client that interacts with Adyen. This class holds the adyen
    logic of Adyen HTTP API communication. This is the object that can maintain
    it's own username, password, merchant_account, hmac, and skin_code. When
    these values aren't within this object, the root adyen module variables will
    be used.

    The public methods, call_api and call_hpp, only return AdyenResult objects.
    Otherwise raising various validation and communication errors.

    Args:
        username (str, optional): Username of webservice user
        password (str, optional): Password of webservice user
        merchant_account (str, optional): Merchant account for requests to be
            placed through
        platform (str, optional): Defaults "test". The Adyen platform to make
            requests against.
        skin_code (str, optional): skin_code to place directory_lookup requests
            and generate hpp signatures with.
        hmac (str, optional): Hmac key that is used for signature calculation.
    """
    def __init__(self, username=None, password=None, review_payout_username=None,
        review_payout_password=None, store_payout_username=None,
        store_payout_password=None, platform=None,
        merchant_account=None, merchant_specific_url=None, skin_code=None, hmac=None):
        self.username = username
        self.password = password
        self.review_payout_username = review_payout_username
        self.review_payout_password = review_payout_password
        self.store_payout_username = store_payout_username
        self.store_payout_password = store_payout_password
        self.platform = platform
        self.merchant_specific_url = merchant_specific_url
        self.hmac = hmac
        self.merchant_account = merchant_account
        self.skin_code = skin_code
        self.http_client = HTTPClient()

    def _determine_api_url(self, platform, service, action):
        """This returns the Adyen API endpoint based on the provided platform,
        service and action.

        Args:
            platform (str): Adyen platform, ie 'live' or 'test'.
            service (str): API service to place request through.
            action (str): the API action to perform.
        """
        base_uri = BASE_PAL_url.format(platform)
        return  '/'.join([base_uri, service, API_VERSION, action])

    def _determine_hpp_url(self, platform, action):
        """This returns the Adyen HPP endpoint based on the provided platform,
        and action.

        Args:
            platform (str): Adyen platform, ie 'live' or 'test'.
            action (str):   the HPP action to perform.
            possible actions: select, pay, skipDetails, directory
        """
        base_uri = BASE_HPP_url.format(platform)
        service = action + '.shtml'
        return  '/'.join([base_uri, service])

    def _review_payout_username(self,**kwargs):
        from Adyen import review_payout_username
        if 'username' in kwargs:
            review_payout_username = kwargs['username']
        elif self.review_payout_username:
            review_payout_username = self.review_payout_username
        if not review_payout_username:
            errorstring = """AdyenInvalidRequestError: Please set your review payout
            webservice username. You can do this by running
            'Adyen.review_payout_username = 'Your payout username' """
            logger.error(errorstring)
            raise AdyenInvalidRequestError(errorstring)

        return review_payout_username

    def _review_payout_pass(self,**kwargs):
        from Adyen import review_payout_password
        if 'password' in kwargs:
            review_payout_password = kwargs["password"]
        elif self.review_payout_password:
            review_payout_password = self.review_payout_password
        if not review_payout_password:
            errorstring = """AdyenInvalidRequestError: Please set your review payout
            webservice password. You can do this by running
            'Adyen.review_payout_password = 'Your payout password'"""
            logger.error(errorstring)
            raise AdyenInvalidRequestError(errorstring)

        return review_payout_password

    def _store_payout_username(self,**kwargs):
        from Adyen import store_payout_username
        if 'username' in kwargs:
            store_payout_username = kwargs['username']
        elif self.store_payout_username:
            store_payout_username = self.store_payout_username
        if not store_payout_username:
            errorstring = """AdyenInvalidRequestError: Please set your store payout
            webservice username. You can do this by running
            'Adyen.store_payout_username = 'Your payout username'"""
            logger.error(errorstring)
            raise AdyenInvalidRequestError(errorstring)

        return store_payout_username

    def _store_payout_pass(self,**kwargs):
        from Adyen import store_payout_password
        if 'password' in kwargs:
            store_payout_password = kwargs["password"]
        elif self.store_payout_password:
            store_payout_password = self.store_payout_password
        if not store_payout_password:
            errorstring = """AdyenInvalidRequestError: Please set your store payout
            webservice password. You can do this by running
            'Adyen.store_payout_password = 'Your payout password'"""
            logger.error(errorstring)
            raise AdyenInvalidRequestError(errorstring)

        return store_payout_password

    def call_api(self, request_data, service, action, idempotency=False,
        **kwargs):
        """This will call the adyen api. username, password, merchant_account,
        and platform are pulled from root module level and or self object.
        AdyenResult will be returned on 200 response. Otherwise, an exception
        is raised.

        Args:
            request_data (dict): The dictionary of the request to place. This
                should be in the structure of the Adyen API.
                https://docs.adyen.com/manuals/api-manual
            service (str): This is the API service to be called.
            action (str): The specific action of the API service to be called
            idempotency (bool, optional): Whether the transaction should be
                processed idempotently.
                https://docs.adyen.com/manuals/api-manual#apiidempotency
        Returns:
            AdyenResult: The AdyenResult is returned when a request was
                succesful.
        """
        from Adyen import username, password, merchant_account, platform

        #username at self object has highest priority. fallback to root module
        #and ensure that it is set.
        if 'username' in kwargs:
            username = kwargs["username"]
        elif service == "Payout":
            if any(substring in action for substring in ["store","submit"]):
                username = self._store_payout_username(**kwargs)
            else:
                username = self._review_payout_username(**kwargs)
        elif self.username:
            username=self.username
        if not username:
            errorstring = """AdyenInvalidRequestError: Please set your webservice username."
             You can do this by running 'Adyen.username = 'Your username'"""
            logger.error(errorstring)
            raise AdyenInvalidRequestError(errorstring)
        #Ensure that username has been removed so as not to be passed to adyen.
        if 'username' in kwargs:
            del kwargs['username']

        #password at self object has highest priority. fallback to root module
        #and ensure that it is set.
        if 'password' in kwargs:
            password = kwargs["password"]
        elif service == "Payout":
            if any(substring in action for substring in ["store","submit"]):
                password = self._store_payout_pass(**kwargs)
            else:
                password = self._review_payout_pass(**kwargs)
        elif self.password:
            password = self.password
        if not password:
            errorstring = """AdyenInvalidRequestError: Please set your webservice password.
             You can do this by running 'Adyen.password = 'Your password'"""
            logger.error(errorstring)
            raise AdyenInvalidRequestError(errorstring)
        #Ensure that password has been removed so as not to be passed to adyen.
        if 'password' in kwargs:
            del kwargs["password"]

        logger.debug('Adyen CLIENT - CALL API')
        logger.debug(password)

        #platform at self object has highest priority. fallback to root module
        #and ensure that it is set to either 'live' or 'test'.
        if 'platform' in kwargs:
            platform = kwargs['platform']
            del kwargs['platform']
        elif self.platform:
            platform = self.platform

        if platform.lower() not in ['live','test']:
            errorstring = "'platform' must be the value of 'live' or 'test'"
            logger.error(errorstring)
            raise ValueError(errorstring)
        elif not isinstance(platform, str):
            errorstring = "'platform' value must be type of string"
            logger.error(errorstring)
            raise TypeError(errorstring)

        message = request_data

        #All API call should have merchantAccount as part of the request.
        #If the merchant account is not in the request, check other locations
        if "merchantAccount" not in message:
            if 'merchant_account' in kwargs:
                message["merchantAccount"] = kwargs["merchant_account"]
                del kwargs["merchant_account"]
            elif self.merchant_account:
                #Try self object
                message["merchantCccount"] = self.merchant_account
            elif merchant_account:
                #Then try root module
                message["merchantAccount"] = merchant_account
            else:
                #merchantAccount has not ben set.
                errorstring = """AdyenInvalidRequestError: No merchantAccount provided. Set one
                with your Adyen.Adyen() class instance.
                merchant_account=\"MerchantAccountName\". Please reach out
                to support@adyen.com if the issue persists."""
                logger.error(errorstring)
                raise AdyenInvalidRequestError(errorstring)

        #Adyen requires this header to be set and uses the combination of
        #merchant account and merchant reference to determine uniqueness.
        headers={}
        if idempotency == True:
            headers['Pragma'] = 'process-retry'

        url = self._determine_api_url(platform, service, action)

        raw_response, raw_request, status_code, headers = self.http_client.request(
            url, json = message, username=username, password=password,
            headers=headers, **kwargs)

        #Creates AdyenResponse if request was successful, raises error if not.
        adyen_result = self._handle_response(url, raw_response, raw_request,
            status_code, headers, message)
        return adyen_result

    def call_hpp(self, request_data, action, hmac_key="", **kwargs):
        """This will call the adyen hpp. hmac_key and platform are pulled from
        root module level and or self object. AdyenResult will be returned on 200 response.
        Otherwise, an exception is raised.

        Args:
            request_data (dict): The dictionary of the request to place. This
                should be in the structure of the Adyen API.
                https://docs.adyen.com/manuals/api-manual
            service (str): This is the API service to be called.
            action (str): The specific action of the API service to be called
            idempotency (bool, optional): Whether the transaction should be
                processed idempotently.
                https://docs.adyen.com/manuals/api-manual#apiidempotency
        Returns:
            AdyenResult: The AdyenResult is returned when a request was
                succesful.
        """
        from Adyen import hmac, platform

        #hmac provided in function has highest priority. fallback to self then
        #root module and ensure that it is set.
        if hmac_key:
            hmac = hmac_key
        elif self.hmac:
            hmac = self.hmac
        elif not hmac:
            errorstring = """Please set an hmac with your Adyen.Adyen class instance.
            'Adyen.hmac = \"!WR#F@...\"' or as an additional
             parameter in the function call ie.
            'Adyen.hpp.directory_lookup(hmac=\"!WR#F@...\"'. Please reach
            out to support@Adyen.com if the issue persists."""
            logger.error(errorstring)
            raise AdyenInvalidRequestError(errorstring)

        #platform provided in self has highest priority, fallback to root module
        #and ensure that it is set.
        if self.platform:
            platform = self.platform
        if platform.lower() not in ['live','test']:
            errorstring = " 'platform' must be the value of 'live' or 'test' "
            logger.error(errorstring)
            raise ValueError(errorstring)
        elif not isinstance(platform, str):
            errorstring = "'platform' must be type string"
            logger.error(errorstring)
            raise TypeError(errorstring)

        message = request_data

        if 'countryCode' not in message:
            print('HPP: Advised to include countryCode with request to make sure local payment methods are found.')

        message["merchantSig"] = util.generate_hpp_sig(message, hmac)
        logger.info(message)

        url = self._determine_hpp_url(platform, action)

        raw_response, raw_request, status_code, headers = self.http_client.request(
            url, data =message, username="", password="", **kwargs)

        #Creates AdyenResponse if request was successful, raises error if not.
        adyen_result = self._handle_response(url, raw_response, raw_request,
            status_code, headers, message)
        return adyen_result

    def hpp_payment(self,request_data, action, hmac_key="", **kwargs):

        from Adyen import hmac, platform

        hmac = self.hmac

        request_data["merchantSig"] = util.generate_hpp_sig(request_data,hmac)
        logger.info('HPP Message')
        logger.info(request_data)

        url = self._determine_hpp_url(platform,action)

        adyen_result = {
            'url': url,
            'message': request_data
        }

        return adyen_result

    def _handle_response(self, url, raw_response, raw_request, status_code, headers, request_dict):
        """This parses the content from raw communication, raising an error if
        anything other than 200 was returned.

        Args:
            url (str): URL where request was made
            raw_response (str): The raw communication sent to Adyen
            raw_request (str): The raw response returned by Adyen
            status_code (int): The HTTP status code
            headers (dict): Key/Value of the headers.
            request_dict (dict): The original request dictionary that was given
                to the HTTPClient.

        Returns:
            AdyenResult: Result object if successful.
        """
        # print status_code
        # print raw_response
        print url
        # print headers
        # print raw_response

        if status_code != 200:
            response = {}
            # If the result can't be parsed into json, most likely is raw html.
            # Some response are neither json or raw html, handle them here:
            try:
                response = json_lib.loads(raw_result)

                self._handle_http_error(url, response, status_code,
                    headers.get('pspReference'), raw_request, raw_response, headers)
            except:

                print response

                response = json_lib.loads(raw_response)

                # Pass raised error to error handler.
                self._handle_http_error(url,response,status_code,headers.get('pspReference'),raw_request,raw_response,headers,request_dict)

                try:
                    if response['errorCode']:
                        return raw_response
                except KeyError:
                    print 'Key Error `errorCode` '
                pass
        else:
            try:
                response = json_lib.loads(raw_response)
                psp = headers.get('pspReference', response.get('pspReference'))
                return AdyenResult(message = response, status_code = status_code,
                    psp = psp, raw_request = raw_request,
                    raw_response = raw_response)
            except ValueError:
                #Couldn't parse json so try to pull error from html.

                error = self._error_from_hpp(raw_response)

                message = request_dict

                reference = message.get("reference",message.get("merchantReference"))

                errorstring = """AdyenInvalidRequestError: Unable to retrieve payment "
                list. Received the error: {}. Please verify your request "
                and try again. If the issue persists, please reach out to "
                support@adyen.com including the "
                merchantReference: {}""".format(error,reference),
                raw_request=message,
                raw_response=raw_response,
                url=url

                logger.error(errorstring)

                raise AdyenInvalidRequestError(errorstring)

    def _handle_http_error(self, url, response_obj, status_code, psp_ref,
            raw_request, raw_response, headers,message):
        """This function handles the non 200 responses from Adyen, raising an
        error that should provide more information.

        Args:
            url (str): url of the request
            response_obj (dict): Dict containing the parsed JSON response from
                Adyen
            status_code (int): HTTP status code of the request
            psp_ref (str): Psp reference of the request attempt
            raw_request (str): The raw request placed to Adyen
            raw_response (str): The raw response(body) returned by Adyen
            headers(dict): headers of the response

        Returns:
            None
        """

        if status_code == 404:
            from Adyen import merchant_specific_url
            if url == merchant_specific_url:
                raise AdyenAPICommunicationError(
                    "Received a 404 for url:'{}'. Please ensure that"
                    " the custom merchant specific url is correct".format(url))
            else:
                raise AdyenAPICommunicationError(
                    "Unexpected error while communicating with Adyen. Please"
                    " reach out to support@adyen.com if the problem persists",
                    raw_request=raw_request,
                    raw_response=raw_response,
                    url=url,
                    psp=psp_ref,
                    headers=headers)
        elif status_code in [400, 422]:
            raise AdyenAPIValidationError(
                "Received validation error with errorCode:{}, message:'{}', "
                "HTTP Code:'{}'. Please verify the values provided. Please reach"
                " out to support@adyen.com if the problem persists, providing "
                "the PSP reference:{}".format( response_obj.get("errorCode"),
                    response_obj.get("message"), status_code, psp_ref),
                result=response_obj,
                error_code=response_obj.get("errorCode"),
                raw_request=raw_request,
                raw_response=raw_response,
                url=url,
                psp=psp_ref,
                headers=headers,
                status_code=status_code)
        elif status_code == 401:
            #print "Message:"
            #print message
            #print "Headers:"
            #print headers
            raise AdyenAPIAuthenticationError(
                "Unable to authenticate with Adyen's Servers. Please verify "
                "the username and password of your webservice user. Please "
                "reach out to your Adyen Admin if the problem persists",
                raw_request=raw_request,
                raw_response=raw_response,
                url=url,
                psp=psp_ref,
                headers=headers)
        elif status_code == 403:
            from Adyen import username
            print raw_request
            # TODO: Json is encoded to single '' which creates an error with .loads
            # How/why does this happen?
            #raw_request = json_lib.loads(raw_request)
            ma = raw_request['merchantAccount']
            if response_obj.get("message")=="Invalid Merchant Account":
                raise AdyenAPIInvalidPermission(
                    "You provided the merchant account:'%s' that doesn't exist "
                    "or you don't have access to it. Please verify the merchant"
                    " account provided. Reach out to support@adyen.com if the "
                    "issue persists" % raw_request['merchantAccount'])
                    # raw_request=raw_request,raw_response=raw_response,url=url,psp=psp_ref,headers=headers
            raise AdyenAPIInvalidPermission(
                "Unable to perform the requested action. message:'{}'. If you "
                "think your webservice user:'{}' might not have the necessary "
                "permissions to perform this request. Please reach out to "
                "support@adyen.com, providing the PSP reference:{}".format(
                response_obj.get("message"),
                username, psp_ref),
                raw_request=raw_request,
                raw_response=raw_response,
                url=url,
                psp=psp_ref,
                headers=headers)
            print 'stuff'

        elif status_code == 422:
            if response_obj.get("message")=="Invalid amount specified":
                raise AdyenAPIInvalidAmount(
                    "Invalid amount specified"
                    "Amount may be improperly formatted, too small or too big."
                    "Print your input amount to console or log to verify"
                    "If the issue persists, contact support@adyen.com"
                    )

        elif status_code == 500:
            if response_obj.get("message")=="Failed to serialize node Failed to parse [123.34] as a Long":
                raise AdyenAPIInvalidFormat(
                    "The paymount amount must be set in cents, and can not contain"
                    " commas or points."
                    )
        else:
            raise AdyenAPICommunicationError(
                "Unexpected error while communicating with Adyen. Received the "
                "response data:'{}', HTTP Code:'{}'. Please reach out to "
                "support@adyen.com if the problem persists with the psp:{}"
                    .format(raw_response,status_code,psp_ref),
                status_code=status_code,
                raw_request=raw_request,
                raw_response=raw_response,
                url=url,
                psp=psp_ref,
                headers=headers)

    def _error_from_hpp(self, html):
        # Must be updated when Adyen response is changed:
        match_obj = re.search('>Error:\s*(.*?)<br', html)
        if match_obj:
            return match_obj.group(1)