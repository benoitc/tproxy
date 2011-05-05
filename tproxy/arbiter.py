# -*- coding: utf-8 -
#
# This file is part of tproxy released under the MIT license. 
# See the NOTICE for more information.

import errno
import logging
import os
import signal
import sys
import time
import traceback

import gevent
from gevent import select

from . import __version__
from . import util
from .pidfile import Pidfile
from .proxy import tcp_listener
from .worker import Worker



class HaltServer(Exception):
    def __init__(self, reason, exit_status=1):
        self.reason = reason
        self.exit_status = exit_status
    
    def __str__(self):
        return "<HaltServer %r %d>" % (self.reason, self.exit_status)

class Arbiter(object):

    WORKER_BOOT_ERROR = 3

    START_CTX = {}
    
    LISTENER = None
    WORKERS = {}    
    PIPE = []

    # I love dynamic languages
    SIG_QUEUE = []
    SIGNALS = map(
        lambda x: getattr(signal, "SIG%s" % x),
        "HUP QUIT INT TERM TTIN TTOU USR1 USR2 WINCH".split()
    )
    SIG_NAMES = dict(
        (getattr(signal, name), name[3:].lower()) for name in dir(signal)
        if name[:3] == "SIG" and name[3] != "_"
    )

    def __init__(self, cfg, script):
        self.cfg = cfg
        self.script = script
        self.num_workers = cfg.workers
        self.address = cfg.address
        self.timeout = cfg.timeout
        self.name = cfg.name

        self.pid = 0
        self.pidfile = None
        self.worker_age = 0
        self.reexec_pid = 0
        self.master_name = "master"
        self.log = logging.getLogger(__name__)

        # get current path, try to use PWD env first
        try:
            a = os.stat(os.environ['PWD'])
            b = os.stat(os.getcwd())
            if a.ino == b.ino and a.dev == b.dev:
                cwd = os.environ['PWD']
            else:
                cwd = os.getcwd()
        except:
            cwd = os.getcwd()
            
        args = sys.argv[:]
        args.insert(0, sys.executable)

        # init start context
        self.START_CTX = {
            "args": args,
            "cwd": cwd,
            0: sys.executable
        }

    def start(self):
        self.pid = os.getpid()
        self.init_signals()
        if not self.LISTENER:
            self.LISTENER = tcp_listener(self.address, self.cfg.backlog)

        if self.cfg.pidfile is not None:
            self.pidfile = Pidfile(self.cfg.pidfile)
            self.pidfile.create(self.pid)

        util._setproctitle("master [%s]" % self.name)
        self.log.info("tproxy %s started" % __version__)
        self.log.info("Listening on %s:%s" % self.address)

    def init_signals(self):
        """\
        Initialize master signal handling. Most of the signals
        are queued. Child signals only wake up the master.
        """
        if self.PIPE:
            map(os.close, self.PIPE)
        self.PIPE = pair = os.pipe()
        map(util.set_non_blocking, pair)
        map(util.close_on_exec, pair)
        map(lambda s: signal.signal(s, self.signal), self.SIGNALS)
        signal.signal(signal.SIGCHLD, self.handle_chld)

    def signal(self, sig, frame):
        if len(self.SIG_QUEUE) < 5:
            self.SIG_QUEUE.append(sig)
            self.wakeup()
        else:
            self.log.warn("Dropping signal: %s" % sig)

    def run(self):
        self.start()
        self.manage_workers()
        while True:
            try:
                self.reap_workers()
                sig = self.SIG_QUEUE.pop(0) if len(self.SIG_QUEUE) else None
                if sig is None:
                    self.sleep()
                    self.murder_workers()
                    self.manage_workers()
                    continue
                
                if sig not in self.SIG_NAMES:
                    self.log.info("Ignoring unknown signal: %s" % sig)
                    continue
                
                signame = self.SIG_NAMES.get(sig)
                handler = getattr(self, "handle_%s" % signame, None)
                if not handler:
                    self.log.error("Unhandled signal: %s" % signame)
                    continue
                self.log.info("Handling signal: %s" % signame)
                handler()  
                self.wakeup()
            except StopIteration:
                self.halt()
            except KeyboardInterrupt:
                self.halt()
            except HaltServer, inst:
                self.halt(reason=inst.reason, exit_status=inst.exit_status)
            except SystemExit:
                raise 
            except Exception:
                self.log.info("Unhandled exception in main loop:\n%s" %  
                            traceback.format_exc())
                self.stop(False)
                if self.pidfile is not None:
                    self.pidfile.unlink()
                sys.exit(-1)
    
    def handle_chld(self, *args):
        "SIGCHLD handling"
        self.wakeup()
        self.reap_workers()
        
    def handle_hup(self):
        """\
        HUP handling.
        - Reload configuration
        - Start the new worker processes with a new configuration
        - Gracefully shutdown the old worker processes
        """
        self.log.info("Hang up: %s" % self.master_name)
        self.reload()
        
    def handle_quit(self):
        "SIGQUIT handling"
        raise StopIteration
    
    def handle_int(self):
        "SIGINT handling"
        self.stop(False)
        raise StopIteration
    
    def handle_term(self):
        "SIGTERM handling"
        self.stop(False)
        raise StopIteration

    def handle_ttin(self):
        """\
        SIGTTIN handling.
        Increases the number of workers by one.
        """
        self.num_workers += 1
        self.manage_workers()
    
    def handle_ttou(self):
        """\
        SIGTTOU handling.
        Decreases the number of workers by one.
        """
        if self.num_workers <= 1:
            return
        self.num_workers -= 1
        self.manage_workers()

    def handle_usr1(self):
        """\
        SIGUSR1 handling.
        Kill all workers by sending them a SIGUSR1
        """
        self.kill_workers(signal.SIGUSR1)
    
    def handle_usr2(self):
        """\
        SIGUSR2 handling.
        Creates a new master/worker set as a slave of the current
        master without affecting old workers. Use this to do live
        deployment with the ability to backout a change.
        """
        self.reexec()
        
    def handle_winch(self):
        "SIGWINCH handling"
        if os.getppid() == 1 or os.getpgrp() != os.getpid():
            self.log.info("graceful stop of workers")
            self.num_workers = 0
            self.kill_workers(signal.SIGQUIT)
        else:
            self.log.info("SIGWINCH ignored. Not daemonized")
    
    def wakeup(self):
        """\
        Wake up the arbiter by writing to the PIPE
        """
        try:
            os.write(self.PIPE[1], '.')
        except IOError, e:
            if e.errno not in [errno.EAGAIN, errno.EINTR]:
                raise
                    
    def halt(self, reason=None, exit_status=0):
        """ halt arbiter """
        self.stop()
        self.log.info("Shutting down: %s" % self.master_name)
        if reason is not None:
            self.log.info("Reason: %s" % reason)
        if self.pidfile is not None:
            self.pidfile.unlink()
        sys.exit(exit_status)

    def sleep(self):
        """\
        Sleep until PIPE is readable or we timeout.
        A readable PIPE means a signal occurred.
        """
        try:
            ready = select.select([self.PIPE[0]], [], [], 1.0)
            if not ready[0]:
                return
            while os.read(self.PIPE[0], 1):
                pass
        except select.error, e:
            if e[0] not in [errno.EAGAIN, errno.EINTR]:
                raise
        except OSError, e:
            if e.errno not in [errno.EAGAIN, errno.EINTR]:
                raise
        except KeyboardInterrupt:
            sys.exit()
            
    
    def stop(self, graceful=True):
        """\
        Stop workers
        
        :attr graceful: boolean, If True (the default) workers will be
        killed gracefully  (ie. trying to wait for the current connection)
        """
        self.LISTENER = None
        sig = signal.SIGQUIT
        if not graceful:
            sig = signal.SIGTERM
        limit = time.time() + self.timeout
        while self.WORKERS and time.time() < limit:
            self.kill_workers(sig)
            gevent.sleep(0.1)
            self.reap_workers()
        self.kill_workers(signal.SIGKILL)

    def reexec(self):
        """\
        Relaunch the master and workers.
        """
        if self.pidfile is not None:
            self.pidfile.rename("%s.oldbin" % self.pidfile.fname)
        
        self.reexec_pid = os.fork()
        if self.reexec_pid != 0:
            self.master_name = "Old Master"
            return
            
        os.environ['TPROXY_FD'] = str(self.LISTENER.fileno())
        os.chdir(self.START_CTX['cwd'])
        self.cfg.pre_exec(self)
        os.execvpe(self.START_CTX[0], self.START_CTX['args'], os.environ)
        
    def reload(self):
        # spawn new workers with new app & conf
        for i in range(self.cfg.workers):
            self.spawn_worker()
        
        # unlink pidfile
        if self.pidfile is not None:
            self.pidfile.unlink()

        # create new pidfile
        if self.cfg.pidfile is not None:
            self.pidfile = Pidfile(self.cfg.pidfile)
            self.pidfile.create(self.pid)
        
        # manage workers
        self.manage_workers() 
        
    def murder_workers(self):
        """\
        Kill unused/idle workers
        """
        for (pid, worker) in self.WORKERS.items():
            try:
                diff = time.time() - os.fstat(worker.tmp.fileno()).st_ctime
                if diff <= self.timeout:
                    continue
            except ValueError:
                continue

            self.log.critical("WORKER TIMEOUT (pid:%s)" % pid)
            self.kill_worker(pid, signal.SIGKILL)
        
    def reap_workers(self):
        """\
        Reap workers to avoid zombie processes
        """
        try:
            while True:
                wpid, status = os.waitpid(-1, os.WNOHANG)
                if not wpid:
                    break
                if self.reexec_pid == wpid:
                    self.reexec_pid = 0
                else:
                    # A worker said it cannot boot. We'll shutdown
                    # to avoid infinite start/stop cycles.
                    exitcode = status >> 8
                    if exitcode == self.WORKER_BOOT_ERROR:
                        reason = "Worker failed to boot."
                        raise HaltServer(reason, self.WORKER_BOOT_ERROR)
                    worker = self.WORKERS.pop(wpid, None)
                    if not worker:
                        continue
                    worker.tmp.close()
        except OSError, e:
            if e.errno == errno.ECHILD:
                pass
    
    def manage_workers(self):
        """\
        Maintain the number of workers by spawning or killing
        as required.
        """
        if len(self.WORKERS.keys()) < self.num_workers:
            self.spawn_workers()

        num_to_kill = len(self.WORKERS) - self.num_workers
        for i in range(num_to_kill, 0, -1):
            pid, age = 0, sys.maxint
            for (wpid, worker) in self.WORKERS.iteritems():
                if worker.age < age:
                    pid, age = wpid, worker.age
            self.kill_worker(pid, signal.SIGQUIT)
            
    def spawn_worker(self):
        self.worker_age += 1
        worker = Worker(self.worker_age, self.pid, self.LISTENER, self.cfg,
                self.script)
        pid = os.fork()
        if pid != 0:
            self.WORKERS[pid] = worker
            return

        # Process Child
        worker_pid = os.getpid()
        try:
            self.log.info("Booting worker with pid: %s" % worker_pid)
            worker.serve_forever()
            sys.exit(0)
        except SystemExit:
            raise
        except KeyboardInterrupt:
            sys.exit(0)
        except:
            self.log.exception("Exception in worker process:")
            if not worker.booted:
                sys.exit(self.WORKER_BOOT_ERROR)
            sys.exit(-1)
        finally:
            self.log.info("Worker exiting (pid: %s)" % worker_pid)
            try:
                worker.tmp.close()
            except:
                pass

    def spawn_workers(self):
        """\
        Spawn new workers as needed.
        
        This is where a worker process leaves the main loop
        of the master process.
        """
        
        for i in range(self.num_workers - len(self.WORKERS.keys())):
            self.spawn_worker()

    def kill_workers(self, sig):
        """\
        Lill all workers with the signal `sig`
        :attr sig: `signal.SIG*` value
        """
        for pid in self.WORKERS.keys():
            self.kill_worker(pid, sig)
                    
    def kill_worker(self, pid, sig):
        """\
        Kill a worker
        
        :attr pid: int, worker pid
        :attr sig: `signal.SIG*` value
         """
        try:
            os.kill(pid, sig)
        except OSError, e:
            if e.errno == errno.ESRCH:
                try:
                    worker = self.WORKERS.pop(pid)
                    worker.tmp.close()
                    return
                except (KeyError, OSError):
                    return
            raise
