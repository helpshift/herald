#!/usr/bin/env python
# -*- coding: utf-8 -*-

from gevent import monkey
monkey.patch_all()

import os
import sys
import imp
import signal
import yaml
import argparse
import gevent
import logging
from functools import partial
from gevent.server import StreamServer
from .baseplugin import HeraldBasePlugin

# TODO: Add tests
#       option to use syslog for logging
#       reloading config + plugins


def start_plugin(plugin):
    """
    Starts the passed in plugin.

    """
    logging.info("starting {}".format(plugin.name))
    plugin.start()


def load_all_plugins(plugins_dir):
    """
    Loads all plugins found in the plugins_dir directory.

    The HeraldBasePlugin class is the "plugin mount" class that
    has a list of all the plugin classes loaded.

    Returns a dict with the plugin name as the key and the reference
    to the respective class as the value.

    """
    logger = logging.getLogger('plugin_loader')

    for fn in os.listdir(plugins_dir):
        if fn.endswith('.py'):
            name = os.path.basename(fn)[:-3]
            try:
                imp.load_source(name, os.path.join(plugins_dir, fn))
            except Exception as e:
                logger.critical('Error loading plugin {}: {} '.format(name, e))
                sys.exit()

    all_plugins = dict()
    for p in HeraldBasePlugin.plugins:
        all_plugins[p.herald_plugin_name] = p

    logger.info(all_plugins)
    return all_plugins


def load_plugin(plugins_list, plugins_config):
    """
    Finds the default plugin, initilizes it and returns the plugin object.

    Plugins are checked for the 'default' key or the first one in the list
    is used.
    Plugin is initialized by passing the entire plugin definition dict found
    in plugins_config.

    """
    logger = logging.getLogger('plugin_loader')
    # check for 'default' flag
    default_plugin = [p for p in plugins_config if 'default' in p]
    # else take the first one in the list
    if not default_plugin:
        default_plugin = plugins_config[0]
    logger.debug('using plugin {}'.format(
        default_plugin['herald_plugin_name']))

    try:
        PluginClass = plugins_list.get(default_plugin['herald_plugin_name'])
    except KeyError:
        logger.critical('Could not load plugin {}'.format(
            default_plugin['herald_plugin_name']))
        sys.exit()

    p = PluginClass(**default_plugin)
    return p

HERALD_STOPPING = False


def stop_services(server, plugin):
    """
    Stop plugin and server gracefully.

    """
    global HERALD_STOPPING
    if not HERALD_STOPPING:
        HERALD_STOPPING = True
        logging.info('stopping plugin {}'.format(plugin.name))
        plugin.stop()
        logging.info('stopping herald server')
        server.stop()
    else:
        logging.info('stop is already in progress')


def setup_handlers(server, plugin):
    """
    Setup signal handlers to stop server gracefully.

    """
    gevent.signal(signal.SIGINT, partial(stop_services, server, plugin))
    gevent.signal(signal.SIGTERM, partial(stop_services, server, plugin))


def setup_logging(args):
    """
    Initialize logger with the requested Loglevel, and the specified
    logformat.

    """
    loglevel = getattr(logging, args.loglevel.upper())
    logformat = '%(asctime)s %(levelname)s [%(name)s] %(message)s'

    logging.basicConfig(format=logformat, level=loglevel)


def load_configuration(config_file):
    """
    Load and return yaml configuration.

    """

    with open(config_file) as config_fd:
        config = yaml.load(config_fd)

    logging.debug('config is {}'.format(config))
    return config


def handle_requests(socket, addr, plugin):
    """
    Handles haproxy agent check connections

    The state to write is obtained from the passed in plugin
    using the `respond` function. The state is suffixed with
    a new line and sent to Haproxy.

    """
    logging.debug("received connect from {}".format(addr))
    state = plugin.respond()
    logging.debug("writing state: {}".format(state))
    socket.send(str(state)+"\n")


def start_server(args, config, plugin):
    """
    Starts the main listener for haporxy agent requests with the handler
    function.

    """
    listen = (config.get('bind', args.bind), config.get('port', args.port))
    handler = partial(handle_requests, plugin=plugin)
    server = StreamServer(listen, handler)

    logging.info("started listening {}".format(listen))
    server.start()
    return server


def main():
    parser = argparse.ArgumentParser(description="Haproxy agent check service")
    parser.add_argument("-c", "--config",
                        default="/etc/herald/config.yml",
                        type=str,
                        help="path to yaml configuraion file")
    parser.add_argument("-b", "--bind",
                        default='0.0.0.0',
                        type=str,
                        help="listen address")
    parser.add_argument("-p", "--port",
                        default=5555,
                        type=int,
                        help="listen port")
    parser.add_argument("-l", "--loglevel",
                        default='info',
                        choices=['info', 'warn', 'debug', 'critical'],
                        type=str,
                        help="set logging level")

    args = parser.parse_args()
    setup_logging(args)

    config = load_configuration(args.config)
    all_plugins = load_all_plugins(config['plugins_dir'])
    plugin = load_plugin(all_plugins, config['plugins'])
    start_plugin(plugin)

    server = start_server(args, config, plugin)
    setup_handlers(server, plugin)
    gevent.wait()

if __name__ == "__main__":
    main()
