#!/usr/bin/env python
# -*- coding: utf-8 -*-

from gevent import monkey
monkey.patch_all()

import urllib2
import socket
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
        req = urllib2.Request(self.url)
        response = ''
        try:
            infourl = urllib2.urlopen(req, timeout=timeout)
        except urllib2.HTTPError as e:
            self.logger.warning('HTTPError: get failed, http code: %s', e.code)
        except urllib2.URLError as e:
            self.logger.critical('URLError: failed to reach a server, '
                                 'reason: %s', e.reason)
        except socket.timeout:
            self.logger.warning('SocketTimeout: the request timed out!')
        else:
            response = ''.join(infourl.readlines())
            self.logger.debug('got response: %s', response)

        if self.is_json:
            try:
                return json.loads(response)
            except ValueError as e:
                    self.logger.critical('json parsing failed on response:'
                                         ' %s' % str(response))
        else:
            return response

    def __str__(self):
        return self.name + ' ' + self.url

    def __unicode__(self):
        return self.name + ' ' + self.url
