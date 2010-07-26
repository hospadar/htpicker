#!/usr/bin/env python

import ConfigParser
import fnmatch
import gtk
import json
import os
import pipes
import stat
import subprocess
import sys
import urlparse
import webkit

gtk.gdk.threads_init()

class WebBrowser(gtk.Window):
    def __init__(self, url, url_handler):
        gtk.Window.__init__(self)

        self.url_handler = url_handler
        self.connect('destroy', self._destroy_cb)

        web_view = webkit.WebView()
        web_view.set_full_content_zoom(True)
        web_view.connect('resource-request-starting', self._resource_cb)
        web_view.open(url)

        settings = web_view.get_settings()
        #settings.set_property("enable-default-context-menu", False)
        #settings.set_property("enable-java-applet", False)
        #settings.set_property("enable-plugins", False)
        settings.set_property("enable-universal-access-from-file-uris", True)
        settings.set_property("enable-xss-auditor", False)
        #settings.set_property("tab-key-cycles-through-elements", False)

        scrolled_window = gtk.ScrolledWindow()
        scrolled_window.set_policy(gtk.POLICY_NEVER, gtk.POLICY_AUTOMATIC)
        scrolled_window.add(web_view)
        scrolled_window.show_all()

        self.add(scrolled_window)
        self.show_all()

    def _destroy_cb(self, window):
        window.destroy()
        gtk.main_quit()

    def _resource_cb(self, view, frame, resource, request, response):
        self.url_handler.handle_request(request)

class URLHandler(object):
    """
    A URL Handler for a given network scheme.

    This assumes URIs of the form "scheme://method".  If you register with the
    scheme "foo", then the URI "foo://bar" will call your bar() method.

    Query string parameters will be translated into Python keyword arguments
    and passed to your method.  If you use a query parameter more than once,
    the multiple values will be rolled up into a list.  E.g:

        yourapp://yourmethod?a=one&a=two&b=three

    will become:

        yourmethod(a=['one', 'two'], b='three')
    """

    def __init__(self, scheme):
        self.scheme = scheme

    def handle_request(self, request):
        # i don't use urlparse.urlsplit() because it doesn't parse the
        # netloc/path of non-http:// URLs in the usual way.
        scheme, rest = request.get_uri().split('://', 1)
        if '?' in rest:
            action, qs = rest.split('?')
        else:
            action = rest
            qs = ''

        q = urlparse.parse_qs(qs)

        params = {}
        for key, values in q.items():
            params[key] = values[0] if len(values) == 1 else values

        if scheme == self.scheme:
            ret = getattr(self, action)(**params)

            if hasattr(self, 'return_uri_filter'):
                new_uri = self.return_uri_filter(ret)
            else:
                new_uri = ret

            if new_uri:
                request.set_uri(new_uri)

default_config = """
# How this config file works:
#
# Each section describes an external program used to play certain files, and
# then lists which files should be played by that program.  Each section has up
# to five lines.  Here is an example, followed by an explanation of each line.
#
# (Line 1) [mplayer]
# (Line 2) command = mplayer -fs {file}
# (Line 3) folders = ~/Videos, ~/Video
# (Line 4) matches = *.avi, *.mkv, *.mpg, *.mp4, *.flv
# (Line 5) icon = video
#
# Line 1 contains the section name.  This is solely for your own reference.
#
# Line 2 contains a command to play files with.  The special term "{file}"
# indicates where the filename should go when executing the command.  Do not
# put quotes around it -- the proper quoting and escaping will be done
# automatically.
#
# Line 3 lists folders (comma-delimited) whose files this command should always
# be used to play.
#
# Line 4 lists file types (filename glob patterns, comma-delimited) that this
# command can play.  These are a fallback, and are only obeyed in folders which
# have not been specifically assigned somewhere in a "folders" line (line 3).
#
# Line 5 states which icon to show for these files.  Options are 'video' and
# 'game'.
#
# A few reasonable defaults have been put here for you:

[mplayer]
command = mplayer -fs {file}
folders = ~/Videos, ~/Video
matches = *.avi, *.mkv, *.mpg, *.mp4, *.flv
icon = video

[zsnes]
command = zsnes {file}
folders = ~/ROMs/SNES
matches = *.smc, *.fig, *.zip
icon = game

[fceu]
command = fceu -fs 1 {file}
folders = ~/ROMs/NES
matches = *.nes *.nes.gz
icon = game
"""

class MyConfigParser(ConfigParser.RawConfigParser):
    def get(self, section, option, default, **kwargs):
        try:
            return ConfigParser.RawConfigParser.get(self, section, option).format(**kwargs)
        except ConfigParser.NoOptionError:
            return default

    def get_list(self, section, option, default, **kwargs):
        val = self.get(section, option, default, **kwargs)
        return map(str.strip, val.split(','))

def is_child_of(dir_in_question, filename):
    d = dir_in_question.rstrip('/') + '/'
    f = filename
    real = os.path.realpath
    common = os.path.commonprefix

    # try both given path and real path for both directory and file.
    if d == common([d, f]): return True
    if d == common([real(d), f]): return True
    if d == common([d, real(f)]): return True
    if d == common([real(d), real(f)]): return True

class MyHandler(URLHandler):
    def __init__(self, scheme):
        super(MyHandler, self).__init__(scheme)
        self.load_config()

    def load_config(self):
        filename = os.path.expanduser("~/.htpickerrc")

        if not os.path.isfile(filename):
            f = open(filename, 'w')
            f.write(default_config)
            f.close()
            print "I have created a ~/.htpickerrc config file for you."
            print "Take a look and edit it to your liking."

        self.config = MyConfigParser()
        self.config.read(filename)

    @staticmethod
    def json_data_uri(data):
        return 'data:application/json;charset=utf-8;base64,' + json.dumps(data).encode('base64')

    def return_uri_filter(self, data):
        return self.json_data_uri(data)

    def get_initial_dir(self):
        d = sys.argv[1] if len(sys.argv) > 1 else os.getcwd()
        return {'initial_dir': d}

    def execute(self, section, fullpath):
        kw = {'file': pipes.quote(fullpath)}
        command = self.config.get(section, 'command', '', **kw)
        if not command:
            print "You need to define a command for '{0}'".format(section)
        else:
            subprocess.Popen(command, shell=True)


    def section_for_file(self, fullpath):
        for section in self.config.sections():
            folders = self.config.get_list(section, 'folders', [])
            for folder in folders:
                if is_child_of(folder, fullpath):
                    return section

        # okay, didn't find it in a folder, so check the patterns

        for section in self.config.sections():
            patterns = self.config.get_list(section, 'matches', [])
            for pattern in patterns:
                if fnmatch.fnmatch(fullpath, pattern):
                    return section

    def play_file(self, fullpath):
        section = self.section_for_file(fullpath)
        if section:
            self.execute(section, fullpath)
        else:
            print "i don't know what command to play this file with: ", fullpath

    def list_files(self, directory):
        base = os.path.abspath(directory)

        files = []

        for i, filename in enumerate(sorted(os.listdir(base))):
            if filename.startswith('.'):
                continue

            fullpath = base + '/' + filename

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
                    icon = self.config.get(section, 'icon', '')
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
            'fullpath': base + '/' + '..',
            'display_name': '&#8593; Parent Folder',
            'type': 'directory',
            'icon': 'directory',
        })

        return { 'files': files }

# bug! alert() hangs the app... sometimes

if __name__ == "__main__":
    handler = MyHandler('htpicker')
    webbrowser = WebBrowser('file://' + os.getcwd() + '/app.html', handler)
    webbrowser.fullscreen()
    gtk.main()
