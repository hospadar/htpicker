#!/usr/bin/env python
# Copyright (C) 2007, 2008, 2009 Jan Michael Alonzo <jmalonzo@gmai.com>
# Copyright (C) 2010 Nick Welch <nick@incise.org>
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin St, Fifth Floor, Boston, MA  02110-1301  USA

import os
import sys
import stat
import json
import gtk
import webkit
import urlparse

gtk.gdk.threads_init()

class WebBrowser(gtk.Window):
    def __init__(self, url, url_handler):
        gtk.Window.__init__(self)

        self.url_handler = url_handler

        web_view = webkit.WebView()
        web_view.set_full_content_zoom(True)

        settings = web_view.get_settings()
        #settings.set_property("enable-default-context-menu", False)
        #settings.set_property("enable-java-applet", False)
        #settings.set_property("enable-plugins", False)
        settings.set_property("enable-universal-access-from-file-uris", True)
        settings.set_property("enable-xss-auditor", False)
        #settings.set_property("tab-key-cycles-through-elements", False)

        web_view.open(url)

        scrolled_window = gtk.ScrolledWindow()
        scrolled_window.props.hscrollbar_policy = gtk.POLICY_AUTOMATIC
        scrolled_window.props.vscrollbar_policy = gtk.POLICY_AUTOMATIC
        scrolled_window.add(web_view)
        scrolled_window.show_all()

        self.add(scrolled_window)

        self.set_default_size(800, 600)
        self.connect('destroy', self._destroy_cb)
        web_view.connect('resource-request-starting', self._resource_cb)

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

class MyHandler(URLHandler):
    @staticmethod
    def json_data_uri(data):
        return 'data:application/json;charset=utf-8;base64,' + json.dumps(data).encode('base64')

    def return_uri_filter(self, data):
        return self.json_data_uri(data)

    def get_initial_dir(self):
        d = sys.argv[1] if len(sys.argv) > 1 else os.getcwd()
        return {'initial_dir': d}

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
            elif stat.S_ISREG(mode):
                filetype = 'file'
            else:
                filetype = 'other'

            files.append({
                'fullpath': fullpath,
                'display_name': (os.path.splitext(filename)[0]
                                 if filetype == 'file' else filename),
                'type': filetype,
            })

        files.insert(0, {
            'fullpath': base + '/' + '..',
            'display_name': '&#8593; Up One Directory',
            'type': 'directory',
        })

        return { 'files': files }
        #return '''data:image/png;base64,
        #        iVBORw0KGgoAAAANSUhEUgAAAAoAAAAKCAYAAACNMs+9AAAABGdBTUEAALGP
        #        C/xhBQAAAAlwSFlzAAALEwAACxMBAJqcGAAAAAd0SU1FB9YGARc5KB0XV+IA
        #        AAAddEVYdENvbW1lbnQAQ3JlYXRlZCB3aXRoIFRoZSBHSU1Q72QlbgAAAF1J
        #        REFUGNO9zL0NglAAxPEfdLTs4BZM4DIO4C7OwQg2JoQ9LE1exdlYvBBeZ7jq
        #        ch9//q1uH4TLzw4d6+ErXMMcXuHWxId3KOETnnXXV6MJpcq2MLaI97CER3N0
        #        vr4MkhoXe0rZigAAAABJRU5ErkJggg=='''

# bug! alert() hangs the app... sometimes

if __name__ == "__main__":
    handler = MyHandler('myapp')
    webbrowser = WebBrowser('file://' + os.getcwd() + '/app.html', handler)
    webbrowser.fullscreen()
    gtk.main()
