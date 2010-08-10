#!/usr/bin/env python

import os
import fnmatch
import itertools
import json
import pipes
import pkg_resources
import stat
import sys
import types
import urllib

from htpicker.browser import URLHandler, URLAction

class MyHandler(URLHandler):
    def __init__(self, scheme, config):
        super(MyHandler, self).__init__(scheme)
        self.config = config

    @URLAction
    def file_resource(self, filepath, mime_type):
        # sadly there appears to be no way to sniff the mime type from the
        # Accept header (or access request headers in general), so we must also
        # ask for it in the URL.
        filename = pkg_resources.resource_filename(__name__, 'data/'+filepath)
        return 'file://' + urllib.quote(filename)

    @staticmethod
    def data_uri(data, mime_type, encoding='utf-8'):
        return 'data:{0};charset={1};base64,'.format(mime_type, encoding) + data.encode('base64')

    @classmethod
    def json_data_uri(cls, data):
        return cls.data_uri(json.dumps(data), 'application/json')

    def return_uri_filter(self, data):
        if isinstance(data, types.DictType):
            return self.json_data_uri(data)
        return data

    @URLAction
    def get_initial_dir(self):
        d = sys.argv[1] if len(sys.argv) > 1 else os.getcwd()
        return {'initial_dir': d}

    @URLAction
    def execute(self, section, fullpath):
        kw = {'file': pipes.quote(fullpath)}
        command = self.config.get_default(section, 'command', '', **kw)
        if not command:
            print "You need to define a command for '{0}'".format(section)
        else:
            #subprocess.Popen(command, shell=True)
            #os.waitpid(proc.pid, 0)

            # the following "should" work but results in a mysterious situation
            # on my eeepc: mplayer outputs one line ("MPlayer SVN-r29237-4.4.1
            # (C) 2000-2009 MPlayer Team") to the shell, and then everything
            # stops.  mplayer is hung, and htpicker has mysteriously received a
            # SIGSTOP from somewhere.  i don't get it AT ALL.

            # the following is uglier but works just fine.
            os.system(command + ' &')


    def section_for_file(self, fullpath):
        for section in self.config.sections():
            # TODO: loading this config file at startup and lower-casing it all
            # then would be faster.  also, use fnmatch.filter.
            patterns = self.config.getlist_default(section, 'matches', [])
            for pattern in patterns:
                pattern = os.path.expanduser(pattern)
                if fnmatch.fnmatch(fullpath.lower(), pattern.lower()):
                    return section

    @URLAction
    def play_file(self, fullpath):
        section = self.section_for_file(fullpath)
        if section:
            self.execute(section, fullpath)
        else:
            print "i don't know what command to play this file with: ", fullpath

    @URLAction
    def list_files(self, directory):
        directory = os.path.abspath(directory)

        files = []

        ignores = self.config.getlist_default('options', 'ignore', [])

        listing = os.listdir(directory)
        ignore_files = set(itertools.chain(*[fnmatch.filter(listing, ignore) for ignore in ignores]))
        listing = set(listing)
        listing.difference_update(ignore_files)
        listing = sorted(listing, key=str.lower)

        for i, filename in enumerate(listing):
            fullpath = directory + '/' + filename

            real = os.path.realpath(os.path.abspath(fullpath))
            try:
                mode = os.stat(real).st_mode
            except OSError:
                # broken symlink, among other things
                continue

            if stat.S_ISDIR(mode):
                filetype = 'directory'
                icon = 'directory'
            elif stat.S_ISREG(mode):
                filetype = 'file'
                section = self.section_for_file(fullpath)
                if section:
                    icon = self.config.get_default(section, 'icon', '')
                else:
                    icon = ''
            else:
                filetype = 'other'


            files.append({
                'fullpath': fullpath,
                'display_name': (os.path.splitext(filename)[0]
                                 if filetype == 'file' else filename),
                'type': filetype,
                'icon': icon,
            })

        files.insert(0, {
            'fullpath': '/' + directory.rsplit('/', 1)[0].lstrip('/'),
            'display_name': '&#8593; Parent Folder',
            'type': 'directory',
            'icon': 'directory',
        })

        return { 'files': files }
