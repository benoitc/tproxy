# -*- coding: utf-8 -
#
# This file is part of tproxy released under the MIT license. 
# See the NOTICE for more information.

import imp
import inspect
import logging
from logging.config import fileConfig
import os
import sys

from . import util
from .arbiter import Arbiter
from .config import Config
from .tools import import_module

class Script(object):
    """ load a python file or module """

    def __init__(self, script_uri, cfg=None):
        self.script_uri = script_uri
        self.cfg = cfg

    def load(self):
        if os.path.exists(self.script_uri):
            script = imp.load_source('_route', self.script_uri)
        else:
            if ":" in self.script_uri:
                parts = self.script_uri.rsplit(":", 1)
                name, objname = parts[0], parts[1]
                mod = import_module(name)

                script_class = getattr(mod, objname)
                if inspect.getargspec(script_class.__init__) > 1:
                    script = script_class(self.cfg)
                else:
                    script=script_class()
            else:
                script = import_module(self.script_uri)

        script.__dict__['__tproxy_cfg__'] = self.cfg
        return script
                        
class Application(object):

    LOG_LEVELS = {
        "critical": logging.CRITICAL,
        "error": logging.ERROR,
        "warning": logging.WARNING,
        "info": logging.INFO,
        "debug": logging.DEBUG
    }

    def __init__(self):
        self.logger = None
        self.cfg = Config("%prog [OPTIONS] script_path")
        self.script = None

    def load_config(self):
         # parse console args
        parser = self.cfg.parser()
        opts, args = parser.parse_args()

        if len(args) != 1:
            parser.error("No script or module specified.")

        script_uri = args[0]
        self.cfg.default_name = args[0]

        # Load conf
        try:
            for k, v in opts.__dict__.items():
                if v is None:
                    continue
                self.cfg.set(k.lower(), v)
        except Exception, e:
            sys.stderr.write("config error: %s\n" % str(e))
            os._exit(1)

        # setup script
        self.script = Script(script_uri, cfg=self.cfg)
        sys.path.insert(0, os.getcwd())


    def configure_logging(self):
        """\
        Set the log level and choose the destination for log output.
        """
        self.logger = logging.getLogger('tproxy')

        fmt = r"%(asctime)s [%(process)d] [%(levelname)s] %(message)s"
        datefmt = r"%Y-%m-%d %H:%M:%S"
        if not self.cfg.logconfig:
            handlers = []
            if self.cfg.logfile != "-":
                handlers.append(logging.FileHandler(self.cfg.logfile))
            else:
                handlers.append(logging.StreamHandler())

            loglevel = self.LOG_LEVELS.get(self.cfg.loglevel.lower(), logging.INFO)
            self.logger.setLevel(loglevel)
            for h in handlers:
                h.setFormatter(logging.Formatter(fmt, datefmt))
                self.logger.addHandler(h)
        else:
            if os.path.exists(self.cfg.logconfig):
                fileConfig(self.cfg.logconfig)
            else:
                raise RuntimeError("Error: logfile '%s' not found." %
                        self.cfg.logconfig)

    def run(self):
        self.load_config()

        if self.cfg.daemon:
            util.daemonize()
            
        else:
            try:
                os.setpgrp()
            except OSError, e:
                if e[0] != errno.EPERM:
                    raise
        
        self.configure_logging()
        try:
            Arbiter(self.cfg, self.script).run()
        except RuntimeError, e:
            sys.stderr.write("\nError: %s\n\n" % e)
            sys.stderr.flush()
            os._exit(1)

def run():
    return Application().run()
