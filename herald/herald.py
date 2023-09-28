#!/usr/bin/env python
# -*- coding: utf-8 -*-
import sys
import os
import signal
import yaml
import argparse
import logging
from functools import partial
from gevent.server import StreamServer
from .baseplugin import HeraldBasePlugin
from gevent import signal_handler as gsignal
from importlib.util import spec_from_file_location, module_from_spec

# TODO: Add tests
# TODO: option to use syslog for logging
# TODO: reloading config + plugins


def start_plugin(plugin):
    """
    Starts the passed in plugin.

    """
    logging.info(f"starting {plugin.name}")
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

    # plugins = {}
    for fn in os.listdir(plugins_dir):
        if fn.endswith('.py'):
            name = os.path.splitext(fn)[0]
            try:
                spec = spec_from_file_location(name, os.path.join(plugins_dir, fn))
                plugin_module = module_from_spec(spec)
                spec.loader.exec_module(plugin_module)
                # plugins[name] = plugin_module
            except Exception as e:
                logger.critical('Error loading plugin {}: {} '.format(name, e))
                sys.exit(1)

    all_plugins = dict()
    for p in HeraldBasePlugin.plugins:
        all_plugins[p.herald_plugin_name] = p

    logger.info(all_plugins)
    return all_plugins

def load_plugin(plugins, config):
    """
    Finds the default plugin, initializes it and returns the plugin object.

    Plugins are checked for the 'default' key or the first one in the list
    is used.
    Plugin is initialized by passing the entire plugin definition dict found
    in plugins_config.

    """
    logger = logging.getLogger('plugin_loader')
    default_plugin = next((p for p in config if 'default' in p), config[0])
    # noinspection PyPep8Naming
    PluginClass = plugins.get(default_plugin['herald_plugin_name'])
    if PluginClass is None:
        logger.critical(f"Could not load plugin {default_plugin['herald_plugin_name']}")
        sys.exit(2)
    return PluginClass(**default_plugin)


HERALD_STOPPING = False


def stop_services(server, plugin):
    """
    Stop plugin and server gracefully.

    """
    global HERALD_STOPPING
    if HERALD_STOPPING:
        logging.info('stop is already in progress')
    else:
        HERALD_STOPPING = True
        logging.info(f'stopping plugin {plugin.name}')
        plugin.stop()
        logging.info('stopping herald server')
        server.stop()


def setup_handlers(server, plugin):
    """
    Setup signal handlers to stop server gracefully.

    """
    gsignal(signal.SIGINT, partial(stop_services, server, plugin))
    gsignal(signal.SIGTERM, partial(stop_services, server, plugin))


def setup_logging(args):
    """
    Initialize logger with the requested Loglevel, and the specified
    logformat.

    """
    loglevel = getattr(logging, args.loglevel.upper())
    log_format = '%(asctime)s %(levelname)s [%(name)s] %(message)s'

    logging.basicConfig(format=log_format, level=loglevel)


def load_configuration(config_file):
    """
    Load and return yaml configuration.

    """
    with open(config_file) as config_fd:
        config = yaml.safe_load(config_fd)

    logging.debug('config is {}'.format(config))
    return config


def handle_requests(socket, addr, plugin):
    """
    Handles haproxy agent check connections

    The state to write is obtained from the passed in plugin
    using the `respond` function. The state is suffixed with
    a new line and sent to Haproxy.

    """
    logging.debug(f"received connect from {addr}")
    state = plugin.respond()
    logging.debug(f"writing state: {state}")
    socket.sendall(f"{state}\n".encode('utf-8'))


def start_server(args, config, plugin):
    """
    Starts the main listener for HAProxy agent requests with the handler
    function.

    """
    address = (config.get('bind', args.bind), config.get('port', args.port))
    server = StreamServer(address, partial(handle_requests, plugin=plugin))
    logging.info(f"started listening {address}")
    server.start()
    return server


def main():
    parser = argparse.ArgumentParser(description="HAProxy agent check service")
    parser.add_argument("-c", "--config",
                        default="/etc/herald/config.yml",
                        type=str,
                        help="path to yaml configuration file")
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
    server.serve_forever()
