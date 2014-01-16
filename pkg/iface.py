#!/usr/bin/python
#
# Copyright 2013.  Cumulus Networks, Inc.
# Author: Roopa Prabhu, roopa@cumulusnetworks.com
#
# iface --
#    interface object
#

import logging
import json

class ifaceFlags():

    NONE = 0x1
    FOLLOW_DEPENDENTS = 0x2

class ifaceStatus():

    """iface status """
    UNKNOWN = 0x1
    SUCCESS = 0x2
    ERROR = 0x3
    NOTFOUND = 0x4

    @classmethod
    def to_str(cls, state):
        if state == cls.UNKNOWN:
            return 'unknown'
        elif state == cls.SUCCESS:
            return 'success'
        elif state == cls.ERROR:
            return 'error'
        elif state == cls.NOTFOUND:
            return 'not found'
    
    @classmethod
    def from_str(cls, state_str):
        if state_str == 'unknown':
            return cls.UNKNOWN
        elif state_str == 'success':
            return cls.SUCCESS
        elif state_str == 'error':
            return cls.ERROR

class ifaceState():

    """ iface states """
    UNKNOWN = 0x1
    NEW = 0x2
    PRE_UP = 0x3
    UP = 0x4
    POST_UP = 0x5
    PRE_DOWN = 0x6
    DOWN = 0x7
    POST_DOWN = 0x8

    @classmethod
    def to_str(cls, state):
        if state == cls.UNKNOWN:
            return 'unknown'
        elif state == cls.NEW:
            return 'new'
        elif state == cls.PRE_UP:
            return 'pre-up'
        elif state == cls.UP:
            return 'up'
        elif state == cls.POST_UP:
            return 'post-up'
        elif state == cls.PRE_DOWN:
            return 'pre-down'
        elif state == cls.POST_DOWN:
            return 'post-down'

    @classmethod
    def from_str(cls, state_str):
        if state_str == 'unknown':
            return cls.UNKNOWN
        elif state_str == 'new':
            return cls.NEW
        elif state_str == 'pre-up':
            return cls.PRE_UP
        elif state_str == 'up':
            return cls.UP
        elif state_str == 'post-up':
            return cls.POST_UP
        elif state_str == 'pre-down':
            return cls.PRE_DOWN
        elif state_str == 'post-down':
            return cls.POST_DOWN


class iface():
    """ config flags """
    AUTO = 0x1
    HOT_PLUG = 0x2

    
    def __init__(self):
        self.name = None
        self.addr_family = None
        self.addr_method = None
        self.config = {}
        self.children = []
        self.state = ifaceState.NEW
        self.status = ifaceStatus.UNKNOWN
        self.flags = 0x0
        self.refcnt = 0
        # dependents that are listed as in the
        # config file
        self.dependents = None
        # All dependents (includes dependents that
        # are not listed in the config file)
        self.realdev_dependents = None
        self.auto = False
        self.classes = []
        self.env = None
        self.config_current = {}
        self.raw_lines = []
        self.linkstate = None

    def inc_refcnt(self):
        self.refcnt += 1

    def dec_refcnt(self):
        self.refcnt -= 1

    def get_refcnt(self):
        return self.refcnt

    def set_refcnt(self, cnt):
        self.refcnt = 0

    def set_name(self, name):
        self.name = name

    def get_name(self):
        return self.name

    def set_addr_family(self, family):
        self.addr_family = family

    def get_addr_family(self):
        return self.addr_family

    def set_addr_method(self, method):
        self.addr_method = method

    def get_addr_method(self):
        return self.addr_method

    def set_config(self, config_dict):
        self.config = config_dict

    def get_config(self):
        return self.config

    def set_config_current(self, config_current):
        self.config_current = config_current

    def get_config_current(self):
        return self.config_current

    def get_auto(self):
        return self.auto

    def set_auto(self):
        self.auto = True

    def reset_auto(self):
        self.auto = False

    def get_classes(self):
        return self.classes

    def set_classes(self, classes):
        """ sets interface class list to the one passed as arg """
        self.classes = classes

    def set_class(self, classname):
        """ Appends a class to the list """
        self.classes.append(classname)

    def belongs_to_class(self, intfclass):
        if intfclass in self.classes:
            return True

        return False

    def add_child(self, child_iface_obj):
        self.children.append(child_iface_obj)

    def get_state(self):
        return self.state

    def get_state_str(self):
        return ifaceState.to_str(self.state)

    def set_state(self, state):
        self.state = state

    def get_status(self):
        return self.status

    def get_status_str(self):
        return ifaceStatus.to_str(self.status)

    def set_status(self, status):
        self.status = status

    def state_str_to_hex(self, state_str):
        return self.state_str_map.get(state_str)

    def set_flag(self, flag):
        self.flags |= flag

    def clear_flag(self, flag):
        self.flags &= ~flag

    def set_dependents(self, dlist):
        self.dependents = dlist

    def get_dependents(self):
        return self.dependents

    def set_realdev_dependents(self, dlist):
        self.realdev_dependents = dlist

    def get_realdev_dependents(self):
        return self.realdev_dependents

    def set_linkstate(self, l):
        self.linkstate = l

    def get_linkstate(self):
        return self.linkstate

    def get_attr_value(self, attr_name):
        config = self.get_config()

        return config.get(attr_name)
    
    def get_attr_value_first(self, attr_name):
        config = self.get_config()

        attr_value_list = config.get(attr_name)
        if attr_value_list is not None:
            return attr_value_list[0]

        return None

    def get_attr_value_n(self, attr_name, attr_index):
        config = self.get_config()

        attr_value_list = config.get(attr_name)
        if attr_value_list is not None:
            try:
                return attr_value_list[attr_index]
            except:
                return None

        return None

    def get_env(self):
        if self.env is None or len(self.env) == 0:
            self.generate_env()
        return self.env

    def set_env(self, env):
        self.env = env

    def generate_env(self):
        env = {}
        config = self.get_config()
        env['IFACE'] = self.get_name()
        for attr, attr_value in config.items():
            attr_env_name = 'IF_%s' %attr.upper()
            env[attr_env_name] = attr_value[0]

        if len(env) > 0:
            self.set_env(env)

    def update_config(self, attr_name, attr_value):
        if self.config.get(attr_name) is None:
            self.config[attr_name] = [attr_value]
        else:
            self.config[attr_name].append(attr_value)

    def update_config_dict(self, attrdict):
        self.config.update(attrdict)

    def update_config_with_status(self, attr_name, attr_value, attr_status=0):
        if attr_value is None:
            attr_value = ''

        if attr_status != 0:
            self.set_status(ifaceStatus.ERROR)
        else:
            if self.get_status() != ifaceStatus.ERROR:
                self.set_status(ifaceStatus.SUCCESS)
        if self.config.get(attr_name) is not None:
            self.config[attr_name].append(attr_value)
        else:
            self.config[attr_name] = [attr_value]

        """ XXX: If status needs to be encoded in the query string
        if attr_status == 0:
            self.set_status(attr
            attr_status_str = ''
        elif attr_status == 0:
            attr_status_str = ' (success)'
        elif attr_status != 0:
            attr_status_str = ' (error)'
        self.config[attr_name] = attr_value + attr_status_str """

    def dump_raw(self, logger):
        indent = '  '
        print (self.raw_lines[0])
        for i in range(1, len(self.raw_lines)):
            print (indent + self.raw_lines[i])
        
    def dump(self, logger):
        indent = '\t'
        logger.info(self.get_name() + ' : {')
        logger.info(indent + 'family: %s' %self.get_addr_family())
        logger.info(indent + 'method: %s' %self.get_addr_method())
        logger.info(indent + 'state: %s'
                %ifaceState.to_str(self.get_state()))
        logger.info(indent + 'status: %s'
                %ifaceStatus.to_str(self.get_status()))
        logger.info(indent + 'refcnt: %d' %self.get_refcnt())
        d = self.get_dependents()
        if d is not None:
            logger.info(indent + 'dependents: %s' %str(d))
        else:
            logger.info(indent + 'dependents: None')

        logger.info(indent + 'realdev dependents: %s'
                    %str(self.get_realdev_dependents()))


        logger.info(indent + 'config: ')
        config = self.get_config()
        if config is not None:
            logger.info(indent + indent + str(config))
        logger.info('}')

    def dump_pretty(self, logger):
        indent = '\t'
        outbuf = 'iface %s' %self.get_name()
        if self.get_addr_family() is not None:
            outbuf += ' %s' %self.get_addr_family()

        if self.get_addr_method() is not None:
            outbuf += ' %s' %self.get_addr_method()

        outbuf += '\n'

        config = self.get_config()
        if config is not None:
            for cname, cvaluelist in config.items():
                for cv in cvaluelist:
                    outbuf += indent + '%s' %cname + ' %s\n' %cv

        #outbuf += ('%s' %indent + '%s' %self.get_state_str() +
        #                ' %s' %self.get_status_str())

        print outbuf


    def dump_json(self, logger):
        json.dumps(self)
