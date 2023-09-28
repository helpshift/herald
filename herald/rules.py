#!/usr/bin/env python
# -*- coding: utf-8 -*-

import re
import logging


class HeraldBaseRules(object):
    """
    Provides common interface and methods to write and process Herald rules.

    """

    def __init__(self, metric):
        """
        `metric` is an expression that is evaluated against `context` during
        evaluation.

        e.g. :
        >>> metric = 'r[msg-rate]'

        """
        self.metric = metric
        self.logger = logging.getLogger(__name__)

    def evaluate_metric(self, context):
        """
        Evaluate metric agaist the passed in context.

        The `context` must be a dictionary.
        """
        assert isinstance(context, dict), \
            'context must be a dictionary, got: {}'.format(context)

        try:
            result = eval(self.metric, {}, context)
        except Exception as e:
            raise Exception(f'Error in evaluating metric: {self.metric} against context: {context}, exception is: {e}')
        return result

    def evaluate(self, context):
        """
        Processs and evaluate the rules based on the passed in context.

        This is the method that the client should call. The rules are evaluated
        in two steps. First, the passed in context is evaluated against the
        metric. Second, the result of the evaluation is processed against the
        rules.

        """
        result = self.evaluate_metric(context)
        return self.process_rules(result)

    def process_rules(value):
        """
        This should implement the rules logic.

        """
        raise NotImplementedError


class HeraldPatterns(HeraldBaseRules):
    """
    Herald patterns rules processsor.

    """

    def __init__(self, rules, metric):
        """
        Instantiate object with the pattern rules and metric.

        rules must be a list of dicts that represent each rule, like so :
        >>> rules = [
                    - ready: '.*healthy.*'
                    - down: '.*unhealthy.*'
                    - drain: '.*maxed.*'
                ]

        """
        super(HeraldPatterns, self).__init__(metric)
        # TODO: add rule validation
        self.rules = rules

    def process_rules(self, value):
        """
        Processes rules against the passed in value.

        Rules are processed in order, and the first match wins.

        `value` should be of type string.

        """
        for rule in self.rules:
            action, pattern = next(iter(rule.items()))
            if re.match(pattern, str(value)):
                return action
        else:
            return None


class HeraldThresholds(HeraldBaseRules):
    """
    Herald threshold rules processsor.

    The support rules are :
        pct   - calculates and returns a percentage (input must be int)
        drain - set to drain if this threshold is met
        down  - set to down if this threshold is met
        up    - set to up if this threshold is met
        and so on

    """

    op_regex = re.compile('^([!<>=]?)([0-9]+)')

    def __init__(self, rules, metric):
        """
        Instantiate threshold object with the threshold rules and metric

        rules must be a list of dicts that represent each rule, like
        so :
        >>> rules = [
                    # respond with "up" if less than 7000
                    - 'up': '<7000'
                    # respond with "drain" if this threshold is met
                    # i.e. greater than 7000
                    - 'drain': '>7000'
                    # respond with "down" if equal to 0
                    - down: 0
                    # Calculate weight percentage based on this number and
                    # respond with that
                    - pct: 7000
                ]

        The supported operators for the thresholds are !, <, > and == (default).

        """
        super(HeraldThresholds, self).__init__(metric)
        self.rules = rules

        self._parsed_rules = []
        # validate thresholds hash and convert to an easier to parse
        # tuple list of the form (action, op, threshold, <optional_field>) :
        # _parsed_rules:
        #   - ('drain', '>', '7000')
        #   - ('pct', '==', '7000', 0)
        for rule in self.rules:
            try:
                # 'pct' is special, it can also have a 'min_threshold_response'
                # key
                if 'pct' in rule:
                    action = 'pct'
                    threshold = rule['pct']
                    min_resp = rule.get('min_threshold_response', 1)
                else:
                    action, threshold = next(iter(rule.items()))

                m = re.match(self.op_regex, str(threshold))
                op, th = m.groups()

                if op == '' or op == '=':
                    op = '=='
                elif op == '!':
                    op = '!='

                # ensure threshold can be converted into int
                # raises ValueError if this fails
                int(th)

                if action == 'pct':
                    parsed_rule = (action, op, str(th), min_resp)
                else:
                    parsed_rule = (action, op, str(th))
                self._parsed_rules.append(parsed_rule)
            except Exception as e:
                raise Exception('Error in parsing threshold rules!: ' + str(e))

    def process_rules(self, value):
        """
        Processes rules against the passed in value.

        Rules are processed in order, and the first match wins.

        `value` must be of type integer.

        """
        try:
            value = float(value)
        except ValueError:
            print(f'value must be of type int or float! value is {value}')
            raise

        for rule in self._parsed_rules:
            action, op, threshold = rule[0], rule[1], rule[2]
            if action == 'pct':
                # calculate the percentage of traffic to be sent based on
                # the threshold. The op value is ignored.
                pct = int(100 - ((value / float(threshold)) * 100))
                if pct <= 0:
                    min_resp = rule[3]
                    self.logger.warn('Pct value {} less than 0, responding with min '
                                     'threshold response {}'.format(pct,
                                                                    min_resp))
                    return str(min_resp) + '%'
                # noop if pct is greater than 100
                elif pct > 100:
                    self.logger.warn('Pct value {} greather thatn 100 responding with '
                                     'empty string (noop)'.format(pct))
                    return ''
                else:
                    return str(pct) + '%'
            else:
                # Evaluate the rule and return the action if True
                if eval('{} {} {}'.format(value, op, threshold)):
                    return action
        else:
            return None
