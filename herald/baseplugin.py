#!/usr/bin/env python
# -*- coding: utf-8 -*-

import time
import logging
import gevent
from .rules import HeraldPatterns, HeraldThresholds


class PluginMount(type):
    """
    Metaclass for registering `plugins`.

    """
    def __init__(cls, name, bases, attrs):
        if not hasattr(cls, 'plugins'):
            # This branch only executes when processing the mount point itself.
            # So, since this is a new plugin type, not an implementation, this
            # class shouldn't be registered as a plugin. Instead, it sets up a
            # list where plugins can be registered later.
            cls.plugins = []
        else:
            # This must be a plugin implementation, which should be registered.
            # Simply appending it to the list is all that's needed to keep
            # track of it later.
            assert hasattr(cls, 'herald_plugin_name'), \
                'Plugin class attribute herald_plugin_name must be defined'

            all_plugin_names = [p.herald_plugin_name for p in cls.plugins]
            assert cls.herald_plugin_name not in all_plugin_names, \
                'Duplicate plugin name detected : %s !'.format(
                    cls.herald_plugin_name)

            cls.plugins.append(cls)


class HeraldBasePlugin(object, metaclass=PluginMount):
    """
    All plugins should inherit from this class.

    Plugins should implement the functions defined below. After importing
    all plugin classes are available as a list in the `plugins` attribute.

    """
    def __init__(self, name, *args, **kwargs):
        self.name = name
        self.state = ''
        self.plugin_enabled = True
        self.logger = logging.getLogger('plugin_'+self.name)

    def read_state(self):
        return self.state

    def write_state(self, value):
        self.state = value

    def start(self):
        raise NotImplementedError

    def respond(self):
        raise NotImplementedError

    def stop(self):
        self.plugin_enabled = False

    def __repr__(self):
        return '<{0}(name="{1}")>'.format(self.__class__.__name__, self.name)

    def __str__(self):
        return self.name

    def __unicode__(self):
        return self.name


class HeraldPlugin(HeraldBasePlugin):
    """
    A herald plugin base class that provides simple interface to write plugins.
    This should not be used directly.

    The subclass has to only implement the `run` method, and `stop` if
    required. Features supported are, async execution, state cacheing,
    stalesnes detection, Herald pattern and threshold detection, logging and
    exception handling.

    The `interval` sets the period for async execution of the `run` method.
    When set to 0 (default) async is disabled, and is instead run inline.

    If `staleness_interval` is not set or set to 0, staleness check is
    disabled, and cached state is returned. The state is marked stale
    if `staleness_interval` seconds have passed since last state update.
    If `staleness_response` is not set or set to 'noop' the plugin will
    respond with an empty string, otherwise respond with the value
    of `staleness_response`.

    `stop_timeout` controls the timeout for graceful shutdown. If
    Greenlet does not stop within timeout, it is killed.

    Threshold and Pattern rules are evaluated against the result.
    Check the docs for the respective class for details on the supported rules.

    `thresholds_metric` and `patterns_metric` should be an expression that gets
    evaluated agianst the plugin result context. The context is available in a
    dictionaray with a special key `r`. For e.g. metric could be

    >>> metric = "r['msg-rate'] * 2"

    If no rules match, `default_response` is returned, which defaults to 'noop'

    """
    herald_plugin_name = 'herald_plugin'

    def __init__(self, *args, **kwargs):
        super(HeraldPlugin, self).__init__(*args, **kwargs)

        self.state = {'timestamp': time.time(), 'value': ''}

        self.interval = kwargs.get('interval', 0)
        assert isinstance(self.interval, int), \
            'interval is not an integer: %s' % self.interval

        self.staleness_interval = kwargs.get('staleness_interval', 0)
        assert isinstance(self.staleness_interval, int), \
            'staleness_interval is not an integer: {}'.format(
                self.staleness_interval)

        self.stop_timeout = kwargs.get('stop_timeout', 10)
        assert isinstance(self.stop_timeout, int), \
            'stop_timeout is not an integer: {}'.format(
                self.stop_timeout)

        self.staleness_response = kwargs.get('staleness_response', '')
        if self.staleness_response == 'noop':
            self.staleness_response = ''

        threshold_rules = kwargs.get('thresholds', [])
        pattern_rules = kwargs.get('patterns', [])

        assert threshold_rules or pattern_rules, \
            'both threshold and pattern rules are not defined!'

        if threshold_rules:
            threshold_metric = kwargs.get('thresholds_metric', 'r')
            self.ht = HeraldThresholds(threshold_rules, threshold_metric)

        if pattern_rules:
            pattern_metric = kwargs.get('patterns_metric', 'r')
            self.hp = HeraldPatterns(pattern_rules, pattern_metric)

        self.default_response = kwargs.get('default_response', '')
        if self.default_response == 'noop':
            self.default_response = ''

    def start(self):
        """
        Starts run with the specified interval.

        If interval is 0 its a no op.

        """
        if not self.interval == 0:
            self.logger.debug(
                "running plugin {} with interval {} seconds".format(
                    self.name, self.interval))
            self.g = gevent.spawn(self.run_with_interval)

    def read_state(self):
        """
        Returns the latest state value.

        """
        return self.state['value']

    def write_state(self, value):
        """
        Write value to state along with the timestamp for staleness detection.

        """
        self.state['value'] = value
        self.state['timestamp'] = time.time()

    def run_with_interval(self):
        """
        Helper to run the `run` function in a gevent loop.

        """
        while self.plugin_enabled:
            try:
                result = self.run()
                state = self.process_rules(result)
                if state:
                    self.write_state(state)
                # if no state means none of the rules matched
                else:
                    self.write_state(self.default_response)
            except Exception as e:
                self.logger.critical('Run failed with : %s' % e)

            gevent.sleep(self.interval)

    def process_rules(self, result):
        """
        Process Herald rules against the passed in result.

        """
        # NOTE: we could have use dict directly here but special chars
        # would have to be converted, like hyphens into underscores for
        # the vars to work in python. This search and replace is expensive
        # when done at runtime.
        #
        # So, store the plugin result in key `r`
        # The only con here would be readability of the metric.
        context = {'r': result}
        state = []
        # process pattern rules
        if hasattr(self, 'hp'):
            pt_result = self.hp.evaluate(context)
            if pt_result:
                state.append(str(pt_result))

        # process threshold rules
        if hasattr(self, 'ht'):
            ht_result = self.ht.evaluate(context)
            if ht_result:
                state.append(str(ht_result))
        # TODO: add state validation here
        # log if two conflicting states are sent, e.g. 'up down'
        # haproxy honours the last state in the list
        return ' '.join(state)

    def run(self):
        """
        This should do the actual work and return the result.

        """
        raise NotImplementedError

    def is_stale(self):
        """
        Check if the current state is stale based on the staleness_interval

        """
        if self.staleness_interval:
            now = time.time()
            return now - self.state['timestamp'] > self.staleness_interval
        else:
            return False

    def respond(self):
        """
        Respond with the final value to send to Haproxy.

        If interval is 0, we need to run the `run` method inline.
        Check for staleness and respond accordingly.

        """
        if self.interval == 0:
            self.run()

        if self.is_stale():
            self.logger.warn('detected stale state, staleness_interval'
                             ' is set to {}s'.format(self.staleness_interval))

            if self.staleness_response and self.staleness_response != 'noop':
                self.logger.warn('responding with staleness_response :'
                                 ' {}'.format(self.staleness_response))
                return self.staleness_response
            else:
                self.logger.warn('staleness_response is not set or set to'
                                 ' "noop", responding with empty string :'
                                 ' {}'.format(self.staleness_response))
                return ''
        else:
            state = self.read_state()
            return state

    def stop(self):
        """
        This will try to stop the plugin gracefully.

        If plugin cannot be stopped within stop_timeout, the Greenlet is
        killed.

        """
# TODO: we can spawn a greenlet to do the timeout and kill logic,
# and HeraldPlugin can expose a method called is_stopped which the
# herald main loop can use to check whether the plugin has stopped or
# not and exit only after all of them have stopped.
# It'll help parallelise things
        # no action required if not async
        if self.interval == 0:
            return
        else:
            self.plugin_enabled = False
            try:
                t = gevent.Timeout(self.stop_timeout)
                t.start()
                self.g.join()
                self.logger.info('stopped')
            except gevent.Timeout:
                self.logger.warn('could not stop within stop_timeout {}, '
                                 'terminating with kill'.format(
                                     self.stop_timeout))
                self.g.kill()
            finally:
                t.cancel()


class ExamplePlugin(HeraldBasePlugin):

    herald_plugin_name = 'herald_example'

    def __init__(self, *args, **kwargs):
        super(ExamplePlugin, self).__init__(*args, **kwargs)

    def start(self):
        self.logger.info("started example plugin")

    def respond(self):
        self.logger.info("responded to request")
        return self.read_state()

    def stop(self):
        self.logger.info("stopping plugin {}".format(self.name))
