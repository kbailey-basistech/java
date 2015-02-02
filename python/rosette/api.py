"""
 ** This data and information is proprietary to, and a valuable trade secret
 ** of, Basis Technology Corp.  It is given in confidence by Basis Technology
 ** and may only be used as permitted under the license agreement under which
 ** it has been distributed, and in no other way.
 **
 ** Copyright (c) 2015 Basis Technology Corporation All rights reserved.
 **
 ** The technical data and information provided herein are provided with
 ** `limited rights', and the computer software provided herein is provided
 ** with `restricted rights' as those terms are defined in DAR and ASPR
 ** 7-104.9(a).
"""

import requests
import logging
import json
from enum import Enum
import sys
import pprint

# this will get more complex in a hurry.
class RosetteException(Exception):
    def __init__(self, status, message, response_message):
        self.status = status
        self.message = message
        self.response_message = response_message
    def __str__(self):
        return self.message + ":\n " + self.response_message

# TODO: Set up OAuth2 session and use it with requests.
# We'll need something to talk to for that, and we won't it for integration tests.
# TODO: when do we turn on compression? Always?

class ResultFormat(Enum):
    SIMPLE = ""
    ROSETTE = "rosette"

class DataFormat(Enum):
    SIMPLE = "text/plain"
    JSON = "application/json"

class InputUnit(Enum):
    DOC = "doc"
    SENTENCE= "sentence"

class MorphologyOutput(Enum):
    LEMMAS = "lemmas"
    PARTS_OF_SPEECH = "parts-of-speech"
    COMPOUND_COMPONENTS = "compound-components"
    HAN_READINGS = "han-readings"
    COMPLETE = "complete"
    
class RaasParamSetBase:
    def __init__(self,repertoire):
        self.__params = {}
        for k in repertoire:
            self.__params[k] = None

    def __setitem__(self, key, val):
        if key not in self.__params:
            raise RosetteException("badKey", "Unknown Rosette parameter key", repr(key))
        self.__params[key] = val

    def __getitem__(self, key):
        if key not in self.__params:
            raise RosetteException("badKey", "Unknown Rosette parameter key", repr(key))
        return self.__params[key]

    def forSerialize(self):
        v = {}
        for (key,val) in self.__params.items():
            if val is None:
                pass
            elif isinstance(val, Enum):
                v[key] = val.value;
            else:
                v[key] = val
        return v

class RaasParameters(RaasParamSetBase):
    def __init__(self):
        RaasParamSetBase.__init__(self, ("content", "contentUri", "contentType", "unit"))

    def serializable(self):
        if self["content"] is not None and self["contentUri"] is not None:
             raise RosetteException("bad argument", "Cannot supply both Content and ContentUri", "bad arguments")
        if self["content"] is None and self["contentUri"] is None:
             raise RosetteException("bad argument", "Must supply one of Content or ContentUri", "bad arguments")
        if self["content"] is not None:
            if not isinstance(self["contentType"], DataFormat):
                raise RosetteException("bad argument", "Parameter 'contentType' not of DataFormat Enum", repr(self["contentType"]))
        if not isinstance(self["unit"], InputUnit):
             raise RosetteException("bad argument", "Parameter 'unit' not of InputUnit Enum", repr(self["unit"]))

        return self.forSerialize()

class RntParameters(RaasParamSetBase):
    def __init__(self):
        RaasParamSetBase.__init__(self, ("name", "targetLanguage", "entityType", "sourceLanguageOfOrigin", "sourceLanguageOfUse", "sourceScript", "targetLanguage", "targetScript", "targetScheme"))

    def serializable(self):
        for n in ("name", "targetLanguage"):  #required
            if self[n] is None:
                raise RosetteException("missing parameter", "Required RNT parameter not supplied", repr(n))
        return self.forSerialize()

class Operator:
    # take a session when we do OAuth2
    def __init__(self, service_url, logger, suburl):
        self.service_url = service_url
        self.logger = logger
        self.suburl = suburl
        self.useMultipart = False

    def __finish_result(self, r, ename):
        code = r.status_code
        theJSON = r.json()
        if code == 200:
            return theJSON
        else:
            if 'message' in theJSON:
                msg = theJSON['message']
            else:
                msg = theJSON['code'] #yuck*1.5
            raise RosetteException(code,
                                   '"' + ename + '" "' + self.suburl + "\" failed to communicate with Raas",
                                   msg)


    def getInfo(self, result_format):
        url = self.service_url + '/' + self.suburl + "/info"
        if result_format == ResultFormat.ROSETTE:
            url = url + "?output=rosette"
        self.logger.info('getInfo: ' + url)
        headers = {'Accept':'application/json'}
        r = requests.get(url, headers=headers)
        return self.__finish_result(r, "getInfo")

    def ping(self):
        url = self.service_url + '/ping'
        self.logger.info('Ping: ' + url)
        headers = {'Accept':'application/json'}
        r = requests.get(url, headers=headers)
        return self.__finish_result(r, "ping")

    def operate(self, parameters, result_format):
        url = self.service_url + '/' + self.suburl
        if result_format == ResultFormat.ROSETTE:
            url = url + "?output=rosette"
        self.logger.info('operate: ' + url)
        params_to_serialize = parameters.serializable()
        headers = {}
        headers['Accept'] = 'application/json'
        headers['Accept-Encoding'] = "gzip"
        if self.useMultipart and 'content' in params_to_serialize:
            cparams = {"unit":params_to_serialize["unit"]}
            dtype = "application/octet-stream"
            data = params_to_serialize["content"]
            files = {'content':('content',data, dtype), 'options':('options', json.dumps(cparams), "application/json")}
            r = requests.post(url, headers=headers, files=files)
        else:
            headers['Content-Type'] = "application/json"
            r = requests.post(url, headers=headers, json=params_to_serialize)

        return self.__finish_result(r, "operate")

class API:
    """
    RaaS Python Client Binding API.
    This binding uses 'requests' (http://docs.python-requests.org/).
    """
    # initial default value for the URL here is wrong.
    def __init__(self, key = None, service_url='http://rosette.basistech.net/raas'):
        """ Supply the key used for the API."""
        self.key = key
        self.service_url = service_url
        self.logger = logging.getLogger('rosette.api')
        self.logger.info('Initialized on ' + self.service_url)
        self.debug = False

    def pinger(self):
        return Operator(self.service_url, self.logger, None)

    def language_detection(self):
        return Operator(self.service_url, self.logger, "language")

    def sentences_split(self):
        return Operator(self.service_url, self.logger, "sentences")

    def tokenize(self):
        return Operator(self.service_url, self.logger, "tokens")

    def morphology(self, subsub):
        if not isinstance(subsub, MorphologyOutput):
            raise RosetteException("bad argument", "Argument not a MorphologyOutput enum object", repr(subsub))
        return Operator(self.service_url, self.logger, "morphology/" + subsub.value)

    def entities(self, linked):
        if  linked:
            return Operator(self.service_url, self.logger, "entities/linked")
        else:
            return Operator(self.service_url, self.logger, "entities")

    def categories(self):
        return Operator(self.service_url, self.logger, "categories")

    def sentiment(self):
        return Operator(self.service_url, self.logger, "sentiment")

    def translate_name(self):
        return Operator(self.service_url, self.logger, "translated-name")
