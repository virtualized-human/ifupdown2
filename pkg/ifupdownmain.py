#!/usr/bin/python
#
# Copyright 2013.  Cumulus Networks, Inc.
# Author: Roopa Prabhu, roopa@cumulusnetworks.com
#
# ifupdownMain --
#    ifupdown main module
#

import os
import re
import imp
import pprint
import logging
import sys, traceback
from statemanager import *
from networkinterfaces import *
from iface import *
from scheduler import *
from collections import deque
from collections import OrderedDict
from graph import *
from sets import Set

class ifupdownMain():

    # Flags
    NODEPENDS = False
    ALL = False
    STATE_CHECK = False

    modules_dir='/etc/network'
    builtin_modules_dir='/usr/share/ifupdownaddons'

    # iface dictionary in the below format:
    # { '<ifacename>' : [<ifaceobject1>, <ifaceobject2> ..] }
    # eg:
    # { 'swp1' : [<ifaceobject1>, <ifaceobject2> ..] }
    #
    # Each ifaceobject corresponds to a configuration block for
    # that interface
    ifaceobjdict = OrderedDict()


    # iface dictionary representing the curr running state of an iface
    # in the below format:
    # {'<ifacename>' : <ifaceobject>}
    ifaceobjcurrdict = OrderedDict()

    # Dictionary representing operation, sub operation and modules
    # for every sub operation
    operations = { 'up' :
                    OrderedDict([('pre-up', OrderedDict({})),
                                 ('up' , OrderedDict({})),
                                 ('post-up' , OrderedDict({}))]),
                   'query-checkcurr' :
                    OrderedDict([('query-checkcurr', OrderedDict({}))]),

                   'query-running' :
                    OrderedDict([('query-running', OrderedDict({}))]),

                   'down' :
                    OrderedDict([('pre-down', OrderedDict({})),
                                 ('down' , OrderedDict({})),
                                 ('post-down' , OrderedDict({}))])}


    def __init__(self, force=False, dryrun=False, nowait=False,
                 perfmode=False, nodepends=False, njobs=1,
                 format='nwifaces', cache=False):
        self.logger = logging.getLogger('ifupdown')

        self.FORCE = force
        self.DRYRUN = dryrun
        self.NOWAIT = nowait
        self.PERFMODE = perfmode
        self.NODEPENDS = nodepends
        self.CACHE = cache
        self._DELETE_DEPENDENT_IFACES_WITH_NOCONFIG = True

        self.ifaces = OrderedDict()
        self.njobs = njobs
        self.pp = pprint.PrettyPrinter(indent=4)
        self.load_modules_builtin(self.builtin_modules_dir)
        self.load_modules(self.modules_dir)

        try:
            self.statemanager = stateManager()
            self.statemanager.read_saved_state()
        except Exception, e:
            # XXX Maybe we should continue by ignoring old state
            self.logger.warning('error reading state (%s)' %str(e))
            raise

    def get_subops(self, op):
        """ Returns sub-operation list """
        return self.operations.get(op).keys()

    def compat_conv_op_to_mode(self, op):
        """ Returns old op name to work with existing scripts """
        if op == 'up':
            return 'start'
        elif op == 'down':
            return 'stop'
        else:
            return op

    def set_force(self, force):
        """ Set force flag. """
        if force == True:
            self.logger.debug('setting force to true')
        self.FORCE = force

    def get_force(self):
        """ return force flag. """
        return self.FORCE

    def set_dryrun(self, dryrun):
        if dryrun == True:
            self.logger.debug('setting dryrun to true')
        self.DRYRUN = dryrun

    def get_dryrun(self):
        return self.DRYRUN

    def get_cache(self):
        return self.CACHE

    def get_ifaceobjdict(self):
        return self.ifaceobjdict

    def set_ifaceobjdict(self, ifaceobjdict):
        del self.ifaceobjdict
        self.ifaceobjdict = ifaceobjdict

    def set_perfmode(self, perfmode):
        if perfmode == True:
            self.logger.debug('setting perfmode to true')
        self.PERFMODE = perfmode

    def get_perfmode(self):
        return self.PERFMODE

    def set_nowait(self, nowait):
        if nowait == True:
            self.logger.debug('setting dryrun to true')
        self.NOWAIT = nowait

    def get_nowait(self):
        return self.NOWAIT

    def set_njobs(self, njobs):
        self.logger.debug('setting njobs to %d' %njobs)
        self.njobs = njobs

    def get_njobs(self):
        return self.njobs

    def get_nodepends(self):
        return self.NODEPENDS

    def set_nodepends(self, nodepends):
        self.logger.debug('setting nodepends to true')
        self.NODEPENDS = nodepends

    def set_iface_state(self, ifaceobj, state, status):
        ifaceobj.set_state(state)
        ifaceobj.set_status(status)
        self.statemanager.update_iface_state(ifaceobj)

    def get_iface_objs(self, ifacename):
        return self.ifaceobjdict.get(ifacename)

    def get_iface_obj_first(self, ifacename):
        ifaceobjs = self.get_iface_objs(ifacename)
        if ifaceobjs is not None:
            return ifaceobjs[0]
        return None

    def get_iface_obj_last(self, ifacename):
        return self.ifaceobjdict.get(ifacename)[-1]

    def create_ifaceobjcurr(self, ifaceobj):
        ifacename = ifaceobj.get_name()
        ifaceobjcurr = self.get_ifaceobjcurr(ifacename)
        if ifaceobjcurr is not None:
            return ifaceobjcurr

        ifaceobjcurr = iface()
        ifaceobjcurr.set_name(ifacename)
        ifaceobjcurr.set_dependents(ifaceobj.get_dependents())
        self.ifaceobjcurrdict[ifacename] = ifaceobjcurr

        return ifaceobj

    def get_ifaceobjcurr(self, ifacename):
        return self.ifaceobjcurrdict.get(ifacename)


    def get_ifaceobjrunning(self, ifacename):
        return self.ifaceobjrunningdict.get(ifacename)

    def get_iface_status(self, ifacename):
        ifaceobjs = self.get_iface_objs(ifacename)
        for i in ifaceobjs:
            if i.get_status() != ifaceStatus.SUCCESS:
                return i.get_status()

        return ifaceStatus.SUCCESS

    def get_iface_refcnt(self, ifacename):
        max = 0
        ifaceobjs = self.get_iface_objs(ifacename)
        for i in ifaceobjs:
            if i.get_refcnt() > max:
                max = i.get_refcnt()
        return max

    def create_n_save_ifaceobj(self, ifacename, increfcnt=False):
        """ creates and returns a fake vlan iface object.
        This was added to support creation of simple vlan
        devices without any user specified configuration.
        """
        ifaceobj = iface()
        ifaceobj.set_name(ifacename)
        if increfcnt == True:
            ifaceobj.inc_refcnt()
        self.ifaceobjdict[ifacename] = [ifaceobj]

    def is_vlan_device(self, ifacename):
        """ Returns true if iface name is a vlan interface.
        
        only supports vlan interfaces of the format <ifacename>.<vlanid>
        
        """
        if (re.search(r'\.', ifacename, 0) is not None):
            return True
        return False

    def preprocess_dependency_list(self, dlist, op):
        """ We go through the dependency list and
            delete or add interfaces from the interfaces dict by
            applying the following rules:
                if flag _DELETE_DEPENDENT_IFACES_WITH_NOCONFIG is True:
                    we only consider devices whose configuration was
                    specified in the network interfaces file. We delete
                    any interface whose config was not specified except
                    for vlan devices. vlan devices get special treatment.
                    Even if they are not present they are created and added
                    to the ifacesdict
                elif flag _DELETE_DEPENDENT_IFACES_WITH_NOCONFIG is False:
                    we create objects for all dependent devices that are not
                    present in the ifacesdict
        """
        del_list = []
        create_list = []

        self.logger.debug('pre-processing dependency list: %s' %list(dlist))
        for d in dlist:
            dilist = self.get_iface_objs(d)
            if dilist == None:
                if (self.is_vlan_device(d) == True or
                        self._DELETE_DEPENDENT_IFACES_WITH_NOCONFIG == False):
                    create_list.append(d)
                else:
                    del_list.append(d)
            else:
                for di in dilist:
                    di.inc_refcnt()

        for d in del_list:
            dlist.remove(d)

        # create fake devices to all dependents that dont have config
        map(lambda i: self.create_n_save_ifaceobj(i, increfcnt=True),
                create_list)

        self.logger.debug('After Processing dependency list: %s'
            %list(dlist))

    def get_dependents(self, ifaceobj, op):
        """ Gets iface dependents by calling into respective modules """
        dlist = None

        self.logger.debug('%s: ' %ifaceobj.get_name() + 'getting dependency')

        # Get dependents for interface by querying respective modules
        subopdict = self.operations.get(op)
        for subop, mdict in subopdict.items():
            for mname, mdata  in mdict.items():
                if mdata.get('ftype') == 'pmodule':
                    module = mdata.get('module')
                    if op == 'query-running':
                        if (hasattr(module,
                            'get_dependent_ifacenames_running') == False):
                            continue
                        dlist = module.get_dependent_ifacenames_running(
                                    ifaceobj)
                    else:
                        if (hasattr(module,
                            'get_dependent_ifacenames') == False):
                            continue
                        dlist = module.get_dependent_ifacenames(ifaceobj,
                                        self.ifaceobjdict.keys())
                    if dlist is not None:
                        ifaceobj.set_realdev_dependents(dlist[:])
                        self.logger.debug('%s: ' %ifaceobj.get_name() +
                                'got dependency list: %s' %str(dlist))
                        break
        return dlist

    def generate_dependency_info(self, ifacenames, dependency_graph, op):
        """ recursive function to generate iface dependency info """

        self.logger.debug('generating dependency info for %s' %str(ifacenames))

        iqueue = deque(ifacenames)
        while iqueue:
            i = iqueue.popleft()

            # Go through all modules and find dependent ifaces
            dlist = None
            ifaceobj = self.get_iface_obj_first(i)
            if ifaceobj is None: 
                continue

            dlist = ifaceobj.get_dependents()
            if dlist is None:
                dlist = self.get_dependents(ifaceobj, op)
            else:
                continue

            if dlist is not None:
                self.preprocess_dependency_list(dlist, op)
                ifaceobj.set_dependents(dlist)
                [iqueue.append(d) for d in dlist]

            if dependency_graph.get(i) is None:
                dependency_graph[i] = dlist

    def is_valid_state_transition(self, ifname, to_be_state):
        return self.statemanager.is_valid_state_transition(ifname,
                to_be_state)

    def save_iface(self, ifaceobj):
        if self.ifaceobjdict.get(ifaceobj.get_name()) is None:
            self.ifaceobjdict[ifaceobj.get_name()] = [ifaceobj]
        else:
            self.ifaceobjdict[ifaceobj.get_name()].append(ifaceobj)

    def read_default_iface_config(self):
        """ Reads default network interface config /etc/network/interfaces. """
        nifaces = networkInterfaces()
        nifaces.subscribe('iface_found', self.save_iface)
        nifaces.load()

    def read_iface_config(self):
        return self.read_default_iface_config()

    def read_old_iface_config(self):
        """ Reads the saved iface config instead of default iface config. """

        # Read it from the statemanager
        self.ifaceobjdict = self.statemanager.get_ifaceobjdict()


    def save_module(self, mkind, msubkind, mname, mftype, module):
        """ saves a module into internal module dict for later use.
        
        mtype - pre-up.d, post-up.d and so on
        mftype - pmodule (python module), bashscript (bash script)
        
        """

        try:
            mmetadata = self.operations[mkind][msubkind].get(mname)
        except KeyError:
            self.logger.warn('unsupported module type %s' %mname)
            return

        if mmetadata is None or mmetadata.get('ftype') != 'pmodule':
            mmetadata = {}
            mmetadata['ftype'] = mftype
            mmetadata['module'] = module
            self.operations[mkind][msubkind][mname] = mmetadata

            self.logger.debug('saved module %s' %mkind +
                             ' %s' %mname + ' %s' %mftype)
        else:
            self.logger.info('ignoring module %s' %mkind + ' %s' %msubkind +
                        ' %s' %mname + ' of type %s' %mftype)


    def load_modules_builtin(self, modules_dir):
        """ load python modules from modules_dir

        Default modules_dir is /usr/share/ifupdownmodules

        """

        self.logger.info('loading builtin modules from %s' %modules_dir)

        if not modules_dir in sys.path:
                sys.path.append(modules_dir)
        try:
            module_list = os.listdir(modules_dir)
            for module in module_list:
                if re.search('.*\.pyc', module, 0) != None:
                    continue

                mname, mext = os.path.splitext(module)
                if mext is not None and mext == '.py':
                    self.logger.info('loading ' + modules_dir + '/' + module)
                    try:
                        m = __import__(mname)
                        mclass = getattr(m, mname)
                    except:
                        raise

                    minstance = mclass(force=self.get_force(),
                                       dryrun=self.get_dryrun(),
                                       nowait=self.get_nowait(),
                                       perfmode=self.get_perfmode(),
                                       cache=self.get_cache())
                    ops = minstance.get_ops()
                    for op in ops:
                        if re.search('query', op) is not None:
                            self.save_module(op, op, mname, 'pmodule',
                                             minstance)
                        elif re.search('up', op) is not None:
                            self.save_module('up', op, mname, 'pmodule',
                                             minstance)
                        else:
                            self.save_module('down', op, mname,
                                             'pmodule', minstance)

        except: 
            raise


    def load_modules(self, modules_dir):
        """ loading user modules from /etc/network/.

        Note that previously loaded python modules override modules found
        under /etc/network if any

        """

        self.logger.info('loading user modules from %s' %modules_dir)
        for op, subops in self.operations.items():
            if re.search('query', op) is not None:
                continue

            for subop in subops.keys():
                msubdir = modules_dir + '/if-%s.d' %subop
                self.logger.info('loading modules under %s ...' %msubdir)
                try:
                    module_list = os.listdir(msubdir)
                    for module in module_list:
                        if re.search('.*\.pyc', module, 0) != None:
                            continue

                        mname, mext = os.path.splitext(module)
                        if mext is not None and mext == '.py':
                            self.logger.debug('loading ' + msubdir + '/' + module)
                            try:
                                m = imp.load_source(module,
                                        msubdir + '/' + module)
                                mclass = getattr(m, mname)
                            except:
                                raise
                            minstance = mclass()
                            self.save_module(op, subop, mname, 'pmodule',
                                                minstance)
                        else:
                            self.save_module(op, subop, mname, 'script',
                                    msubdir + '/' + module)
                except: 
                    raise

        #self.logger.debug('modules ...')
        #self.pp.pprint(self.operations)

        # For query, we add a special entry, basically use all 'up' modules
        self.operations['query'] = self.operations.get('up')


    def conv_iface_namelist_to_objlist(self, intf_list):
        for intf in intf_list:
            iface_obj = self.get_iface(intf)
            if iface_obj == None:
                raise ifupdownInvalidValue('no iface %s', intf)

            iface_objs.append(iface_obj)

        return iface_objs


    def run_without_dependents(self, op, ifacenames):
        ifaceSched = ifaceScheduler(force=self.FORCE)

        self.logger.debug('run_without_dependents for op %s' %op +
                ' for %s' %str(ifacenames))

        if ifacenames == None:
            raise ifupdownInvalidValue('no interfaces found')

        return ifaceSched.run_iface_list(self, ifacenames, op)


    def run_with_dependents(self, op, ifacenames):
        dependency_graph = {}
        ret = 0
        self.logger.debug('run_with_dependents for op %s'
                          %op + ' for %s' %str(ifacenames))

        ifaceSched = ifaceScheduler()

        if ifacenames is None:
            ifacenames = self.ifaceobjdict.keys()

        # generate dependency graph of interfaces
        self.generate_dependency_info(ifacenames, dependency_graph, op)

        if self.logger.isEnabledFor(logging.DEBUG) == True:
            self.logger.debug('dependency graph:')
            self.pp.pprint(dependency_graph)

        if self.njobs > 1:
            ret = ifaceSched.run_iface_dependency_graph_parallel(self,
                        dependency_graph, op)
        else:
            ret = ifaceSched.run_iface_dependency_graph(self,
                        dependency_graph, op)
        return ret

    def print_dependency(self, op, ifacenames, format):
        dependency_graph = {}
        if ifacenames is None:
            ifacenames = self.ifaceobjdict.keys()

        # generate dependency graph of interfaces
        self._DELETE_DEPENDENT_IFACES_WITH_NOCONFIG = False
        self.generate_dependency_info(ifacenames, dependency_graph, op)

        if format == 'list':
            self.pp.pprint(dependency_graph)
        elif format == 'dot':
            indegrees = {}
            map(lambda i: indegrees.update({i :
                self.get_iface_refcnt(i)}),
                dependency_graph.keys())
            graph.generate_dots(dependency_graph, indegrees)

    def validate_ifaces(self, ifacenames):
        """ validates interface list for config existance.
       
        returns -1 if one or more interface not found. else, returns 0

        """

        err_iface = ''
        for i in ifacenames:
            ifaceobjs = self.get_iface_objs(i)
            if ifaceobjs is None:
                err_iface += ' ' + i

        if len(err_iface) != 0:
            self.logger.error('did not find interfaces: %s' %err_iface)
            return -1

        return 0


    def iface_whitelisted(self, auto, allow_classes, excludepats, ifacename):
        """ Checks if interface is whitelisted depending on set of parameters.


        interfaces are checked against the allow_classes and auto lists.

        """

        # If the interface matches
        if excludepats is not None and len(excludepats) > 0:
            for e in excludepats:
                if re.search(e, ifacename) is not None:
                    return False

        ifaceobjs = self.get_iface_objs(ifacename)
        if ifaceobjs is None:
            self.logger.debug('iface %s' %ifacename + ' not found')
            return False

        # We check classes first
        if allow_classes is not None and len(allow_classes) > 0:
            for i in ifaceobjs:
                if (len(i.get_classes()) > 0):
                    common = Set([allow_classes]).intersection(
                                Set(i.get_classes()))
                    if len(common) > 0:
                        return True
            return False

        if auto == True:
            for i in ifaceobjs:
                if i.get_auto() == True:
                    return True
            return False

        return True

    def generate_running_env(self, ifaceobj, op):
        """ Generates a dictionary with env variables required for
        an interface. Used to support script execution for interfaces.
        """

        cenv = None
        iface_env = ifaceobj.get_env()
        if iface_env is not None:
            cenv = os.environ
            if cenv is not None:
                cenv.update(iface_env)
            else:
                cenv = iface_env

            cenv['MODE'] = self.compat_conv_op_to_mode(op)

        return cenv


    def run(self, op, auto=False, allow_classes=None,
            ifacenames=None, excludepats=None,
            format=None, printdependency=None):
        """ main ifupdown run method """

        if auto == True:
            self.logger.debug('setting flag ALL')
            self.ALL = True

        # Only read new iface config for 'up'
        # operations. For 'downs' we only rely on
        # old state
        if op == 'query-running':
            # create fake devices to all dependents that dont have config
            map(lambda i: self.create_n_save_ifaceobj(i), ifacenames)
        elif op == 'up' or op[:5] == 'query':
            try:
                self.read_iface_config()
            except Exception, e:
                raise
        elif op == 'down':
            # for down we need to look at old state
            self.logger.debug('down op, looking at old state ..')

            if len(self.statemanager.get_ifaceobjdict()) > 0:
                self.read_old_iface_config()
            elif self.FORCE == True:
                # If no old state available 
                self.logger.info('old state not available. ' +
                     'Force option set. Loading new iface config file')
                try:
                    self.read_iface_config()
                except Exception, e:
                    raise Exception('error reading iface config (%s)'
                                    %str(e))
            else:
                raise Exception('old state not available...aborting.' +
                        ' try running with --force option')


        if ifacenames is not None and op != 'query-running':
            # If iface list is given, always check if iface is present
           if self.validate_ifaces(ifacenames) != 0:
               raise Exception('all or some interfaces not found')

        # if iface list not given by user, assume all from config file
        if ifacenames is None: ifacenames = self.ifaceobjdict.keys()

        # filter interfaces based on auto and allow classes
        if op == 'query-running':
            filtered_ifacenames = ifacenames
        else:
            filtered_ifacenames = [i for i in ifacenames
                if self.iface_whitelisted(auto, allow_classes,
                        excludepats, i) == True]

        if len(filtered_ifacenames) == 0:
                raise Exception('no ifaces found matching ' +
                        'given allow lists')

        if op == 'query':
            return self.print_ifaceobjs_raw(filtered_ifacenames)
        elif op == 'query-presumed':
            return self.print_ifaceobjs_saved_state_pretty(
                                    filtered_ifacenames)
        elif op == 'query-presumeddetailed':
            return self.print_ifaceobjs_saved_state_detailed_pretty(
                                    filtered_ifacenames)

        if printdependency is not None:
            self.print_dependency(op, filtered_ifacenames, printdependency)
            return

        #if op.split('-')[0] == 'query' or self.NODEPENDS == True:
        if op.split('-')[0] == 'query' or self.NODEPENDS == True:
            self.run_without_dependents(op, filtered_ifacenames)
        else:
            self.run_with_dependents(op, filtered_ifacenames)

        if op == 'query-checkcurr':
            # print curr state of all interfaces
            ret = self.print_ifaceobjscurr_pretty(filtered_ifacenames)
            if ret != 0:
                # if any of the object has an error, signal that silently
                raise Exception('')
        elif op == 'query-running':
            # print curr state of all interfaces
            self.print_ifaceobjsrunning_pretty(filtered_ifacenames)
            return

        # Update persistant iface states
        try:
            if self.ALL == True:
                self.statemanager.flush_state(self.ifaceobjdict)
            else:
                self.statemanager.flush_state()
        except Exception, e:
            if self.logger.isEnabledFor(logging.DEBUG):
                t = sys.exc_info()[2]
                traceback.print_tb(t)
            self.logger.warning('error saving state (%s)' %str(e))


    def up(self, auto=False, allow=None, ifacenames=None,
           excludepats=None, printdependency=None):
        return self.run('up', auto, allow, ifacenames,
                        excludepats=excludepats,
                        printdependency=printdependency)

    def down(self, auto=False, allow=None, ifacenames=None, excludepats=None):
        return self.run('down', auto, allow, ifacenames,
                        excludepats=excludepats);

    def query(self, op, auto=False, allow_classes=None, ifacenames=None,
              excludepats=None, printdependency=None,
              format=None):
        """ main ifupdown run method """
        if auto == True:
            self.logger.debug('setting flag ALL')
            self.ALL = True

        if op == 'query-running':
            self._DELETE_DEPENDENT_IFACES_WITH_NOCONFIG = False
            # create fake devices to all dependents that dont have config
            map(lambda i: self.create_n_save_ifaceobj(i), ifacenames)
        else:
            try:
                self.read_iface_config()
            except Exception:
                raise

        if ifacenames is not None and op != 'query-running':
            # If iface list is given, always check if iface is present
           if self.validate_ifaces(ifacenames) != 0:
               raise Exception('all or some interfaces not found')

        # if iface list not given by user, assume all from config file
        if ifacenames is None: ifacenames = self.ifaceobjdict.keys()

        # filter interfaces based on auto and allow classes
        if op == 'query-running':
            filtered_ifacenames = ifacenames
        else:
            filtered_ifacenames = [i for i in ifacenames
                if self.iface_whitelisted(auto, allow_classes,
                        excludepats, i) == True]

        if len(filtered_ifacenames) == 0:
                raise Exception('no ifaces found matching ' +
                        'given allow lists')

        if op == 'query':
            return self.print_ifaceobjs_raw(filtered_ifacenames)
        elif op == 'query-presumed':
            return self.print_ifaceobjs_saved_state_pretty(
                                    filtered_ifacenames)
        elif op == 'query-presumeddetailed':
            return self.print_ifaceobjs_saved_state_detailed_pretty(
                                    filtered_ifacenames)

        if printdependency is not None:
            self.print_dependency(op, filtered_ifacenames, printdependency)
            return

        if self.NODEPENDS == True:
            self.run_without_dependents(op, filtered_ifacenames)
        else:
            self.run_with_dependents(op, filtered_ifacenames)

        if op == 'query-checkcurr':
            ret = self.print_ifaceobjscurr_pretty(filtered_ifacenames)
            if ret != 0:
                # if any of the object has an error, signal that silently
                raise Exception('')
        elif op == 'query-running':
            self.print_ifaceobjsrunning_pretty(filtered_ifacenames)
            return

    def reload(self, auto=False, allow=None,
               ifacenames=None, excludepats=None):
        """ main ifupdown run method """
        allow_classes = []

        self.logger.debug('reloading interface config ..')

        if auto == True:
            self.logger.debug('setting flag ALL')
            self.ALL = True

        try:
            self.read_iface_config()
        except Exception, e:
            raise

        # Save a copy of new iface objects
        new_ifaceobjdict = self.get_ifaceobjdict()

        if len(self.statemanager.get_ifaceobjdict()) > 0:
            # if old state is present, read old state and mark op for 'down'
            # followed by 'up' aka: reload
            self.read_old_iface_config()
            op = 'reload'
        else:
            # oldconfig not available, continue with 'up' with new config
            op = 'up'

        if ifacenames is None: ifacenames = self.ifaceobjdict.keys()
        if (op == 'reload' and ifacenames is not None and
                len(ifacenames) != 0):
            filtered_ifacenames = [i for i in ifacenames
                               if self.iface_whitelisted(auto, allow_classes,
                               excludepats, i) == True]
            ifacedownlist = Set(filtered_ifacenames).difference(
                                Set(new_ifaceobjdict.keys()))
            if ifacedownlist is not None and len(ifacedownlist) > 0:
                self.logger.debug('bringing down interfaces: %s'
                                  %str(ifacedownlist))
                if self.NODEPENDS == True:
                    self.run_without_dependents('down', ifacedownlist)
                else:
                    self.run_with_dependents('down', ifacedownlist)

                # Update persistant iface states
                try:
                    if self.ALL == True:
                        self.statemanager.flush_state(self.ifaceobjdict)
                    else:
                        self.statemanager.flush_state()
                except Exception, e:
                    if self.logger.isEnabledFor(logging.DEBUG):
                        t = sys.exc_info()[2]
                        traceback.print_tb(t)
                    self.logger.warning('error saving state (%s)' %str(e))

        # Now, run up with new dict
        self.set_ifaceobjdict(new_ifaceobjdict)
        ifacenames = self.ifaceobjdict.keys()
        filtered_ifacenames = [i for i in ifacenames
                               if self.iface_whitelisted(auto, allow_classes,
                               excludepats, i) == True]

        self.logger.debug('bringing up interfaces: %s'
                          %str(filtered_ifacenames))
        if self.NODEPENDS == True:
            self.run_without_dependents('up', filtered_ifacenames)
        else:
            self.run_with_dependents('up', filtered_ifacenames)

        # Update persistant iface states
        try:
            if self.ALL == True:
                self.statemanager.flush_state(self.get_ifaceobjdict())
            else:
                self.statemanager.flush_state()
        except Exception, e:
            if self.logger.isEnabledFor(logging.DEBUG):
                t = sys.exc_info()[2]
                traceback.print_tb(t)
                self.logger.warning('error saving state (%s)' %str(e))

    def dump(self):
        """ all state dump """

        print 'ifupdown object dump'
        print self.pp.pprint(self.modules)
        print self.pp.pprint(self.ifaces)
        self.state_manager.dump()

    def print_state(self, ifacenames=None):
        self.statemanager.dump(ifacenames)

    def print_ifaceobjs_raw(self, ifacenames):
        for i in ifacenames:
            ifaceobjs = self.get_iface_objs(i)
            for i in ifaceobjs:
                i.dump_raw(self.logger)
                print '\n'

    def print_ifaceobjs_pretty(self, ifacenames):
        for i in ifacenames:
            ifaceobjs = self.get_iface_objs(i)
            for i in ifaceobjs:
                i.dump_pretty(self.logger)
                print '\n'

    def dump_ifaceobjs(self, ifacenames):
        for i in ifacenames:
            ifaceobjs = self.get_iface_objs(i)
            for i in ifaceobjs:
                i.dump(self.logger)
                print '\n'

    def print_ifaceobjscurr_pretty(self, ifacenames, format=None):
        """ Dumps current running state of interfaces.

        returns 1 if any of the interface has an error,
        else returns 0
        """
        ret = 0
        for i in ifacenames:
            ifaceobj = self.get_ifaceobjcurr(i)
            if ifaceobj is None: continue
            if ifaceobj.get_status() == ifaceStatus.NOTFOUND:
                print 'iface %s' %ifaceobj.get_name() + ' (not found)'
                ret = 1
                continue
            elif ifaceobj.get_status() == ifaceStatus.ERROR:
                ret = 1
            if format is None or format == 'nwifaces':
                ifaceobj.dump_pretty(self.logger)
            else:
                ifaceobj.dump_json(self.logger)

            dlist = ifaceobj.get_dependents()
            if dlist is None or len(dlist) == 0: continue
            self.print_ifaceobjscurr_pretty(dlist, format)

        return ret

    def print_ifaceobjsrunning_pretty(self, ifacenames, format=None):
        for i in ifacenames:
            ifaceobj = self.get_iface_obj_first(i)
            if ifaceobj.get_status() == ifaceStatus.NOTFOUND:
                print 'iface %s' %ifaceobj.get_name() + ' (not found)'
                continue

            if format is None or format == 'nwifaces':
                ifaceobj.dump_pretty(self.logger)
            elif format == 'json':
                ifaceobj.dump_json(self.logger)

            dlist = ifaceobj.get_dependents()
            if dlist is None or len(dlist) == 0: continue
            self.print_ifaceobjsrunning_pretty(dlist, format)
        return

    def print_ifaceobjs_saved_state_pretty(self, ifacenames):
        self.statemanager.print_state_pretty(ifacenames, self.logger)

    def print_ifaceobjs_saved_state_detailed_pretty(self, ifacenames):
        self.statemanager.print_state_detailed_pretty(ifacenames, self.logger)
