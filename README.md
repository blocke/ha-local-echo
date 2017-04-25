# This project has been abandoned. Home Assistant now includes built in Hue hub emulation which makes this project now pointless.

Please see: <https://home-assistant.io/components/emulated_hue/> or an alternative project is <https://github.com/home-assistant/homebridge-homeassistant>

# ha-local-echo
Home automation tool to allow you to control your devices in Home Assistant with voice commands from your Amazon Echo. HA-Local-Echo (HALE) integrates with Home Assistant through it's API and emulates a subset of the Philips Hue local network API for the Echo. This emulation of the Hue API means Amazon Echo can discover and control what it thinks are light bulbs but are really Home Assistant device entities.

This tool was inspired by *ha-bridge*, *amazon-echo-ha-bridge*, and *hasska*. HALE is a Python based implementation of the idea that is intended to tightly integrate with Home Assistant and leverage the Home Assistant API for configuration.

The only configuration needed for HALE is to tell it the IP address of the network interface to listen on and to tell it how to connect to Home Assistant. All smart home device configuration is pulled from Home Assistant via the Home Assistant API and is managed there. If you change your Home Assistant configuration restart the HALE script after restarting Home Assistant to have HALE pull the new devices.

## Installation
HALE requires a modern version of Python3 and the excellent Flask and Requests libraries. It is probably a good idea to use virtualenv and run HALE from it.

To install the dependencies:
```
pip install flask
pip install requests
```

Edit the HALE script and configure the following variables at the top:

```
# Config
HA_BASE_URL = "http://127.0.0.1:8123"
HA_API_KEY = None
LISTEN_IP = "192.168.10.250"
HTTP_LISTEN_PORT = 8000
```

HALE needs to listen on an IP address that is on the same network (or VLAN) as the Amazon Echo device. SSDP/UPNP discovery over multicast is used by the Echo to find the Philips Hue hubs that HALE is pretending to be. If you are using a firewall on the system HALE is running on then make sure to allow the needed traffic through the firewall. The following are example Linux iptables rules:

```
iptables -A INPUT -i wlan1 -m conntrack --ctstate NEW -p tcp --dport 8000 -j ACCEPT
iptables -A INPUT -i wlan1 -m conntrack --ctstate NEW -p udp -d 239.255.255.250 --dport 1900 -j ACCEPT
```

Start the HALE script and it will reach out to the Home Assistant API and discover devices to be exposed to the Amazon Echo.

In order for a Home Assistant entity to be made available to voice commands via the Echo the Home Assistant entity will need to be customized to include a *echo* value set to true in the HA configuration file. Additionally you may optionally set an *echo_name* to give it a more voice command friendly name to use.

```
homeassistant:
  customize:
    switch.ac_control:
      echo: true
      echo_name: air conditioner
```

Up to 49 entities can be made available via an instance of HALE. This limit is a limitation in the Amazon Echo's usage of the Hue API.

You can run the HALE script in whichever way you prefer. Here is an example systemd unit file that shows invoking the script within a virtualenv environment:

```
[Unit]
Description=HA-Local-Echo Bridge
After=network.target

[Service]
Type=simple
ExecStart=/opt/ha-local-echo/hale-py3env/bin/python3 /opt/ha-local-echo/ha-local-echo.py
User=ha-local-echo
Restart=always
RestartSec=2
StartLimitInterval=0
SyslogIdentifier=ha-local-echo

[Install]
WantedBy=multi-user.target
```


## Usage

The standard Alexa voice commands for turning on, turning off, and dimming lights can be used for devices exposed via HALE. Sadly some voice commands are far less reliable than others and this is a problem on the Alexa voice processing side and nothing HALE has control over. The most reliable forms from my testing seems to be "Alexa, Turn On <foo>" and "Alexa, Turn Off <foo>".



