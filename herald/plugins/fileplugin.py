#!/usr/bin/env python
# -*- coding: utf-8 -*-

import json
from herald.baseplugin import HeraldPlugin


class FilePlugin(HeraldPlugin):
    """
    Reads state from the provided file. If `is_json` is set file
    contents are parsed using json.

    """
    # TODO: Make this generic for any file like object, like sockets

    herald_plugin_name = 'herald_file'

    def __init__(self, *args, **kwargs):
        super(FilePlugin, self).__init__(*args, **kwargs)
        self.file_path = kwargs['file_path']
        self.is_json = kwargs.get('is_json', False)

    def run(self):
        try:
            with open(self.file_path) as f:
                file_contents = f.read()
            self.logger.debug('read %s from file %s' % (file_contents,
                                                        self.file_path))
        except IOError as e:
                self.logger.critical('could not read file, error: %s' % str(e))
                return

        if self.is_json:
            try:
                return json.loads(file_contents)
            except ValueError as e:
                    self.logger.critical('json parsing failed on file'
                                         ' contents: %s' % str(file_contents))
        else:
            return file_contents

    def __str__(self):
        return self.name + ' ' + self.file_path

    def __unicode__(self):
        return self.name + ' ' + self.file_path
