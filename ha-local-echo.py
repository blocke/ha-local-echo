#!/usr/bin/env python3

#
# https://github.com/blocke/ha-local-echo
# Released under MIT license - Copyright 2016 - Bruce A. Locke <blocke@shivan.org>
#

import requests
import flask
import json
import threading
import socket
import socketserver
import time
import json
import datetime
import re
import sys
import zlib

# Config
HA_BASE_URL = "http://127.0.0.1:8123"
HA_API_KEY = None
LISTEN_IP = "192.168.10.250"
HTTP_LISTEN_PORT = 8000

#
# Home Assistant API Usage
#
class HomeAssistant:
    entities = {}
    headers = {}

    def __init__(self, base_url=HA_BASE_URL):
        self.base_url = base_url
        self.fetch_entities()

        self.headers = { 'content-type': 'application/json' }

        if HA_API_KEY is not None:
            self.headers['x-ha-access'] = HA_API_KEY

    def fetch_entities(self):
        print("Fetching Home Assistant entities...")
        req = requests.get("{0}/api/states".format(self.base_url), headers=self.headers)
        states_json = json.loads(req.text)

        entries = 0

        for state in states_json:

            if ('view' in state['attributes']) and (state['attributes']['view'] == True):
                # Ignore entities that are views
                continue

            domain_type = state['entity_id'].split('.')[0].lower()

            # Only handle specific entity types
            if domain_type in ['switch', 'light', 'script', 'scene', 'group', 'input_boolean', 'media_player']:

                if not (('echo' in state['attributes']) and (state['attributes']['echo'] == True)):
                    # Ignore all entities missing an explicit echo attribute set to True
                    continue

                # API limit in Echo implementation
                entries += 1
                if entries > 49:
                    print("FATAL ERROR: Echo only supports up to 49 devices per Hue hub via local API")
                    sys.exit(1)

                # If echo_name set use it
                if 'echo_name' in state['attributes']:
                    new_entity_name = state['attributes']['echo_name']
                # If no friendly name specified create one from entity id
                elif 'friendly_name' in state['attributes']:
                    new_entity_name = state['attributes']['friendly_name'].lower()
                else:
                    new_entity_name = state['entity_id'].split('.')[1:].join().replace('_',' ').lower()

                # Filter the friendly entity name so that it only contains letters and spaces
                new_entity_name = re.sub("[^\w\ ]+", "", new_entity_name, re.U)

                # Really dumb way of creating stable unique_ids
                unique_id = zlib.crc32(state['entity_id'].encode('utf-8'))

                self.entities[unique_id] = {}
                self.entities[unique_id]['name'] = new_entity_name
                self.entities[unique_id]['entity_id'] = state['entity_id']
                self.entities[unique_id]['domain_type'] = domain_type
                self.entities[unique_id]['cached_on'] = False
                self.entities[unique_id]['cached_bri'] = 0

                print('Adding {0}: entity_id "{1}" with spoken name "{2}"'.format(unique_id, state['entity_id'], new_entity_name))

        # Did we find any eligible entities?
        if len(self.entities) == 0:
            print("FATAL ERROR: No eligible entities found. Did you configure Home Assistant?")
            sys.exit(1)

        print("Using {0} entities from Home Assistant\n".format(len(self.entities)))


    def turn_on(self, entity_id):
        print('Asking HA to turn ON entity "{0}"'.format(entity_id))

        req = requests.post("{0}/api/services/homeassistant/turn_on".format(self.base_url), json={'entity_id': entity_id}, headers=self.headers)

        if req.status_code != 200:
            print("Call to HA failed: {0}".format(req.json()))
            flask.abort(500)

    def turn_off(self, entity_id):
        print('Asking HA to turn OFF entity "{0}"'.format(entity_id))

        req = requests.post("{0}/api/services/homeassistant/turn_off".format(self.base_url), json={'entity_id': entity_id}, headers=self.headers)

        if req.status_code != 200:
            print("Call to HA failed: {0}".format(req.json()))
            flask.abort(500)

    def turn_brightness(self, entity_id, brightness):
        print('Asking HA to turn ON entity "{0}" and set brightness to {1}'.format(entity_id, brightness))

        req = requests.post("{0}/api/services/homeassistant/turn_on".format(self.base_url), json={'entity_id': entity_id, 'brightness': brightness}, headers=self.headers)

        if req.status_code != 200:
            print("Call to HA failed: {0}".format(req.json()))
            flask.abort(500)


#
# UPNP Responder Thread Object
#
class UPNPResponderThread(threading.Thread):

    UPNP_RESPONSE = """HTTP/1.1 200 OK
CACHE-CONTROL: max-age=60
EXT:
LOCATION: http://{0}:{1}/description.xml
SERVER: FreeRTOS/6.0.5, UPnP/1.0, IpBridge/0.1
ST: urn:schemas-upnp-org:device:basic:1
USN: uuid:Socket-1_0-221438K0100073::urn:schemas-upnp-org:device:basic:1

""".format(LISTEN_IP, HTTP_LISTEN_PORT).replace("\n", "\r\n").encode('utf-8')

    stop_thread = False

    def run(self):

        # Listen for UDP port 1900 packets sent to SSDP multicast address
        print("UPNP Responder Thread started...")
        ssdpmc_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

        # Required for receiving multicast
        ssdpmc_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        ssdpmc_socket.setsockopt(socket.SOL_IP, socket.IP_MULTICAST_IF, socket.inet_aton(LISTEN_IP))
        ssdpmc_socket.setsockopt(socket.SOL_IP, socket.IP_ADD_MEMBERSHIP, socket.inet_aton("239.255.255.250") + socket.inet_aton(LISTEN_IP))

        ssdpmc_socket.bind(("239.255.255.250", 1900))

        while True:
            try:
                data, addr = ssdpmc_socket.recvfrom(1024)
            except socket.error as e:
                if stop_thread == True:
                    print("UPNP Reponder Thread closing socket and shutting down...")
                    ssdpmc_socket.close()
                    return  
                print ("UPNP Responder socket.error exception occured: {0}".format(e.__str__))

            # SSDP M-SEARCH method received - respond to it unicast with our info
            if "M-SEARCH" in data.decode('utf-8'):
                print("UPNP Responder sending response to {0}:{1}".format(addr[0], addr[1]))
                ssdpout_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                ssdpout_socket.sendto(self.UPNP_RESPONSE, addr)
                ssdpout_socket.close()

    def stop(self):
        # Request for thread to stop
        self.stop_thread = True

# Global Variables
ha = HomeAssistant()
upnp_responder = UPNPResponderThread()
app = flask.Flask(__name__)

#
# Flask Webserver Routes
#

#
# /description.xml required as part of Hue hub discovery
#
DESCRIPTION_XML_RESPONSE = """<?xml version="1.0" encoding="UTF-8" ?>
<root xmlns="urn:schemas-upnp-org:device-1-0">
<specVersion>
<major>1</major>
<minor>0</minor>
</specVersion>
<URLBase>http://{0}:{1}/</URLBase>
<device>
<deviceType>urn:schemas-upnp-org:device:Basic:1</deviceType>
<friendlyName>HA-Echo ({0})</friendlyName>
<manufacturer>Royal Philips Electronics</manufacturer>
<manufacturerURL>http://www.philips.com</manufacturerURL>
<modelDescription>Philips hue Personal Wireless Lighting</modelDescription>
<modelName>Philips hue bridge 2015</modelName>
<modelNumber>BSB002</modelNumber>
<modelURL>http://www.meethue.com</modelURL>
<serialNumber>1234</serialNumber>
<UDN>uuid:2f402f80-da50-11e1-9b23-001788255acc</UDN>
<presentationURL>index.html</presentationURL>
<iconList>
<icon>
<mimetype>image/png</mimetype>
<height>48</height>
<width>48</width>
<depth>24</depth>
<url>hue_logo_0.png</url>
</icon>
<icon>
<mimetype>image/png</mimetype>
<height>120</height>
<width>120</width>
<depth>24</depth>
<url>hue_logo_3.png</url>
</icon>
</iconList>
</device>
</root>
""".format(LISTEN_IP, HTTP_LISTEN_PORT)

@app.route('/description.xml', strict_slashes=False, methods = ['GET'])
def hue_description_xml():
    return flask.Response(DESCRIPTION_XML_RESPONSE, mimetype='text/xml')

#
# Device enumeration request from Echo
#
@app.route('/api/<token>/lights', strict_slashes=False, methods = ['GET'])
@app.route('/api/<token>/lights/', strict_slashes=False, methods = ['GET'])
def hue_api_lights(token):
    json_response = {}

    for id_num in ha.entities.keys():

        json_response[id_num] = {'state': {'on': ha.entities[id_num]['cached_on'], 'bri': ha.entities[id_num]['cached_bri'], 'hue':0, 'sat':0, 'effect': 'none', 'ct': 0, 'alert': 'none', 'reachable':True}, 'type': 'Dimmable light', 'name': ha.entities[id_num]['name'], 'modelid': 'LWB004', 'manufacturername': 'Philips', 'uniqueid': id_num, 'swversion': '66012040'}

    return flask.Response(json.dumps(json_response), mimetype='application/json')

#
# Change state request from Echo
#
@app.route('/api/<token>/lights/<int:id_num>/state', methods = ['PUT'])
def hue_api_put_light(token, id_num):
    request_json = flask.request.get_json(force=True)
    print("Echo PUT {0}/state: {1}".format(id_num, request_json))

    # Echo requested device be turned "on"
    if 'on' in request_json and request_json['on'] == True:
        ha.turn_on(ha.entities[id_num]['entity_id'])
        ha.entities[id_num]['cached_on'] = True
        return flask.Response(json.dumps([{'success': {'/lights/{0}/state/on'.format(id_num): True }}]), mimetype='application/json', status=200)

    # Scripts and scenes can't really be turned off so treat 'off' as 'on'
    if 'on' in request_json and request_json['on'] == False and ha.entities[id_num]['domain_type'] in ['script', 'scene']:
        ha.turn_on(ha.entities[id_num]['entity_id'])
        ha.entities[id_num]['cached_on'] = False
        return flask.Response(json.dumps([{'success': {'/lights/{0}/state/on'.format(id_num): True }}]), mimetype='application/json', status=200)

    # Echo requested device be turned "off"
    if 'on' in request_json and request_json['on'] == False:
        ha.turn_off(ha.entities[id_num]['entity_id'])
        ha.entities[id_num]['cached_on'] = False
        return flask.Response(json.dumps([{'success': {'/lights/{0}/state/on'.format(id_num): False }}]), mimetype='application/json', status=200)

    # Echo requested a change to brightness
    if 'bri' in request_json:
        ha.turn_brightness(ha.entities[id_num]['entity_id'], request_json['bri'])
        ha.entities[id_num]['cached_bri'] = request_json['bri']
        return flask.Response(json.dumps([{'success': {'/lights/{0}/state/bri': request_json['bri']}}]), mimetype='application/json', status=200)

    print("Unhandled API request: {0}".format(request_json))
    flask.abort(500)

#
# Echo pulls individual device state to make sure command went through
#
@app.route('/api/<token>/lights/<int:id_num>', strict_slashes=False, methods = ['GET'])
def hue_api_individual_light(token, id_num):
    json_response = {}


    json_response = {'state': {'on': ha.entities[id_num]['cached_on'], 'bri': ha.entities[id_num]['cached_bri'], 'hue':0, 'sat':0, 'effect': 'none', 'ct': 0, 'alert': 'none', 'reachable':True}, 'type': 'Dimmable light', 'name': ha.entities[id_num]['name'], 'modelid': 'LWB004', 'manufacturername': 'Philips', 'uniqueid': id_num, 'swversion': '66012040'}

    return flask.Response(json.dumps(json_response), mimetype='application/json')

#
# Catch error state
#
@app.route('/api/<token>/groups', strict_slashes=False)
@app.route('/api/<token>/groups/0', strict_slashes=False)
def hue_api_groups_0(token):
    print("ERROR: If echo requests /api/groups that usually means it failed to parse /api/lights.")
    print("This probably means the Echo didn't like something in a name.")
    return flask.abort(500)

#
# Assign a dummy username to Echo if it asks for one
#
@app.route('/api', strict_slashes=False, methods = ['POST'])
def hue_api_create_user():
    request_json = flask.request.get_json(force=True)

    if 'devicetype' not in request_json:
        return flask.abort(500)

    print("Echo asked to be assigned a username")
    return flask.Response(json.dumps([{'success': {'username': '12345678901234567890'}}]), mimetype='application/json')

#
# Startit all up...
#
def main():
    global upnp_responder
    global app

    upnp_responder.start()

    print("Starting Flask for HTTP listening on {0}:{1}...".format(LISTEN_IP, HTTP_LISTEN_PORT))
    app.run(host=LISTEN_IP, port=HTTP_LISTEN_PORT, threaded=True, use_reloader=False)


if __name__ == "__main__":
    main()

