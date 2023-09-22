#!/usr/bin/env python
# -*- coding: utf-8 -*-

#from gevent import monkey
#monkey.patch_all()

import requests
import json
from herald.baseplugin import HeraldPlugin


class HTTPPlugin(HeraldPlugin):
    """
    Reads state from the passed in URI

    """
    herald_plugin_name = 'herald_http'

    def __init__(self, *args, **kwargs):
        super(HTTPPlugin, self).__init__(*args, **kwargs)
        self.url = kwargs['url']
        self.is_json = kwargs.get('is_json', False)

    def run(self, timeout=10):
        response = ''
        try:
            infourl = requests.get(self.url, timeout=timeout)
            infourl.raise_for_status()
            response = infourl.text
            self.logger.debug('got response: %s', response)
        except requests.HTTPError as e:
            self.logger.warning('HTTPError: get failed, http code: %s', e.response.status_code)
        except requests.RequestException as e:
            self.logger.critical('RequestException: failed to reach a server, reason: %s', e)
        except requests.Timeout:
            self.logger.warning('Timeout: the request timed out!')

        if self.is_json:
            try:
                return json.loads(response)
            except ValueError as e:
                self.logger.critical(f'json parsing failed on response: {response}')
        else:
            return response

    def __str__(self):
        return self.name + ' ' + self.url

    def __unicode__(self):
        return self.name + ' ' + self.url
