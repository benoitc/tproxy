# -*- coding: utf-8 -
#
# This file is part of tproxy released under the MIT license. 
# See the NOTICE for more information.

import imp
import logging
from logging.config import fileConfig
import os
import sys

from . import util
from .arbiter import Arbiter
from .config import Config

class Script(object):
    """ load a python file or module """

    def __init__(self, script_uri):
        self.script_uri = script_uri

    def load(self):
        if os.path.exists(self.script_uri):
            script = imp.load_source('_route', self.script_uri)
        else:
            script = __import__(self.script_uri)
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

        # parse console args
        parser = self.cfg.parser()
        opts, args = parser.parse_args()

        if len(args) != 1:
            parser.error("No script or module specified.")

        script_uri = args[0]
        self.cfg.default_name = args[0]
        self.script = Script(script_uri)

        sys.path.insert(0, os.getcwd())

        # Load conf
        for k, v in opts.__dict__.items():
            if v is None:
                continue
            self.cfg.set(k.lower(), v)

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
        if self.cfg.daemon:
            util.daemonize()
        
        self.configure_logging()
        try:
            Arbiter(self.cfg, self.script).run()
        except RuntimeError, e:
            sys.stderr.write("\nError: %s\n\n" % e)
            sys.stderr.flush()
            sys.exit(1)


def run():
    return Application().run()
