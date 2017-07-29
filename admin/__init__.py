# -*- coding: utf-8 -*-

### common imports
from flask import Blueprint, abort
from domogik.common.utils import get_packages_directory
from domogik.admin.application import render_template
from domogik.admin.views.clients import get_client_detail, get_client_devices
from jinja2 import TemplateNotFound

### package specific imports
#import os
import traceback
from flask_wtf import Form
from wtforms import TextField, validators
from flask import request

import subprocess
import json
from datetime import datetime

import zmq
from zmq.eventloop.ioloop import IOLoop
from domogikmq.reqrep.client import MQSyncReq
from domogikmq.message import MQMessage

'''

'''

# -------------------------------------------------------------------------------------------------
def get_flows(devices):
    flowslist = []
    for a_device in devices:
        if a_device["sensors"]["flow"]["last_received"]:     # Can be 'None'
            last_received = datetime.fromtimestamp(a_device["sensors"]["flow"]["last_received"]).strftime("%e %b %k:%M")
        else:
            last_received = ""

        flowslist.append(
            {"name": a_device["name"], 
             "sensorid": a_device["sensors"]["flow"]["id"],
             "date": last_received,
             "value": a_device["sensors"]["flow"]["last_value"],             
             "hourflow": a_device["sensors"]["hourflow"]["last_value"],
             "dayflow": a_device["sensors"]["dayflow"]["last_value"],
             "monthflow": a_device["sensors"]["monthflow"]["last_value"]
             })
    return flowslist

# -------------------------------------------------------------------------------------------------
def get_allsensors():
    counterdttype = ["DT_Number", "DT_Counter", "DT_ActiveEnergy", "DT_kActiveEnergy", "DT_kMeter", "DT_VolumeLiter", "DT_VolumeM3"]
    cli = MQSyncReq(zmq.Context())
    msg = MQMessage()

    deviceslist = {}
    msg.set_action('device.get')
    res = cli.request('admin', msg.get(), timeout=10)
    if res is not None:
        if 'device.result' in res.get():
            deviceslist = json.loads(res.get()[1])["devices"]

    print("\n\ndeviceslist = \n%s\n\n" % format(deviceslist))

    sensorslist = []
    for a_device in deviceslist:
        for a_sensor in a_device["sensors"]:
            stype = a_device["sensors"][a_sensor]["data_type"]
            if stype in counterdttype and "flowmeter" not in a_device["client_id"]:
                sensorid = a_device["sensors"][a_sensor]["id"]
                sensorslist.append({
                                "plugin": a_device["client_id"], 
                                "device": a_device["name"], 
                                "name" : a_device["sensors"][a_sensor]["name"],
                                "id": sensorid
                                })
                                
    print("\n\nsensorslist = \n%s\n\n" % format(sensorslist))
    return sensorslist


# -------------------------------------------------------------------------------------------------
def reqMQFilterSensorHistory(id, ts, interval, selector):
    # get the filtered and calculated history starting from/to a certain timestamp
    cli = MQSyncReq(zmq.Context())
    msg = MQMessage()
    msg.set_action('sensor_history.get')
    msg.add_data('mode', 'filter')      # Like REST functions sensorHistory_from_filter and sensorHistory_from_to_filter
    msg.add_data('sensor_id', id) 
    msg.add_data('from', ts)            # 
    #msg.add_data('to', 1500847199)     # now
    msg.add_data('interval', interval)  # 'minute|hour|day|week|month|year'
    msg.add_data('selector', selector)  # 'min|max|avg|sum'
    try:
        sensor_history = cli.request('admin', msg.get(), timeout=15).get()
    except AttributeError:
        print("AttributeError for get FilterSensorHistory")
        return []
    if 'sensor_history.result' in sensor_history:
        historyvalues = json.loads(sensor_history[1])
        if historyvalues["status"]:
            return historyvalues["values"]["values"]
        else:
            print("Status : False, Reason : '%s'" % historyvalues["reason"])
            return []
    else:
        print("No Result for FilterSensorHistory: '%s'" % format(sensor_history))
        return []
            

# -------------------------------------------------------------------------------------------------
def get_errorlog(log):
    print("Log file = %s" % log)
    errorlog = subprocess.Popen(['/bin/egrep', 'ERROR|WARNING', log], stdout=subprocess.PIPE)
    output = errorlog.communicate()[0]
    if not output:
        output = "No ERROR or WARNING"
    if isinstance(output, str):
        output = unicode(output, 'utf-8')
    return output


# -------------------------------------------------------------------------------------------------
### common tasks
package = "plugin_flowmeter"
template_dir = "{0}/{1}/admin/templates".format(get_packages_directory(), package)
static_dir = "{0}/{1}/admin/static".format(get_packages_directory(), package)
logfile = "/var/log/domogik/{0}.log".format(package)

plugin_flowmeter_adm = Blueprint(package, __name__,
                        template_folder = template_dir,
                        static_folder = static_dir)



# -------------------------------------------------------------------------------------------------
@plugin_flowmeter_adm.route('/<client_id>')
def index(client_id):

    detail = get_client_detail(client_id)       # flowmeter plugin configuration
    devices = get_client_devices(client_id)     # flowmeter plugin devices list
    #print("\n\nget_client_devices = \n%s\n\n" % format(devices))
    
    try:
        return render_template('plugin_flowmeter.html',
            clientid = client_id,
            client_detail = detail,
            mactive = "clients",
            active = 'advanced',
            flowslist = get_flows(devices),
            sensorslist = get_allsensors(),
            logfile = logfile, 
            errorlog = get_errorlog(logfile))

    except TemplateNotFound:
        abort(404)


# -------------------------------------------------------------------------------------------------
@plugin_flowmeter_adm.route('/<client_id>/log')
def log(client_id):
    clientid = client_id
    detail = get_client_detail(client_id)
    with open(logfile, 'r') as contentLogFile:
        content_log = contentLogFile.read()
        if not content_log:
            content_log = "Empty log file"
        if isinstance(content_log, str):
            content_log = unicode(content_log, 'utf-8')
    try:
        return render_template('plugin_flowmeter_log.html',
            clientid = client_id,
            client_detail = detail,
            mactive = "clients",
            active = 'advanced',
            logfile = logfile,
            contentLog = content_log)

    except TemplateNotFound:
        abort(404)


