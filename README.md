# Herald

Herald is a load feedback and check agent for Haproxy.

The agent is configured in Haproxy using the `agent-check` server option. Once enabled haproxy periodically (`agent-inter`) connects to the backend on the configured port (`agent-port`) and acts on the response.

The response can either indicate an action to perform, such as `MAINT`, `UP`, `DRAIN`, etc or change the weight of the respective backend with a percentage, say `75%`. Check Haproxy documentation [here](https://cbonte.github.io/haproxy-dconv/1.6/configuration.html#5.2-agent-check) for more details.

There are many use cases for using the agent, load feedback being an obvious one.

## Goals

* Flexible and easy to configure
* Extensible using plugins
* High performance

## Install

We recommend using pip to install in a virtualenv :

```
$ virtualenv herald
$ pip install herald
```

## Configuration

In your haproxy backend add the agent-check configuration like so :

```
frontend myservice
        bind *:8004
        maxconn 20000
        option tcp-smart-accept
        default_backend myservers

backend myservers
        balance leastconn
        option tcp-smart-connect
        fullconn 20000
        server myserver01 myserver01:8081       maxconn 10000 weight 100 check agent-check agent-port 5555
        server myserver02 myserver02:8081       maxconn 10000 weight 100 check agent-check agent-port 5555
        server myserver03 myserver03:8081       maxconn 10000 weight 100 check agent-check agent-port 5555
```

This instructs haproxy to connect to agent on port **5555**.

On the backend servers, run herald with the following configuration :

```yaml
---
name: myservice
bind: 0.0.0.0
port: 5555
plugins_dir: /etc/herald/plugins
plugins:
  - name: myservice_plugin
    herald_plugin_name: herald_http
    url: 'http://localhost:8081/health_check'
    is_json: yes
    stop_timeout: 60
    interval: 30
    staleness_interval: 120
    staleness_response: noop
    thresholds_metric: "r['msg-pre-second']"
    thresholds:
      - pct: 7000
        min_threshold_response: 1
    default_response: noop
```

Herald reads from `/etc/herald/config.yml` by default. The plugins are bundled in herald.plugins, which can be symlinked in `/etc/herald/plugins`.

Check the *example_config.yml* file for detailed configuration options.

With this configuration, herald will poll the health check url every **30s**. Note that the response is also cached to avoid hitting the health check url too often.

## Plugins

The *herald_http* and *herald_file* plugins are provided in *herald/plugins* directory. These should serve most use cases. The plugin code is simple and easy to follow; Writing additional plugins should be very easy.

The following features are provided by the plugin framework :

* Check result cacheing
* Json parsing and processing parsed data using any python dict expression
* Arthmetic expressions on the result
* Calculate weight percentage on the result
* Regex pattern matching on the result
