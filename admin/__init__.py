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
from datetime import datetime, timedelta

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
             "deviceid" : a_device["id"],
             "sensorid": a_device["sensors"]["flow"]["id"],
             "dtype": a_device["sensors"]["flow"]["data_type"],
             "date": last_received,
             "flow": a_device["sensors"]["flow"]["last_value"],             
             "hourflow": a_device["sensors"]["hourflow"]["last_value"],
             "dayflow": a_device["sensors"]["dayflow"]["last_value"],
             "monthflow": a_device["sensors"]["monthflow"]["last_value"]
             })
    return flowslist

# -------------------------------------------------------------------------------------------------
def get_allsensors():
    counterdttype = ["DT_Number", "DT_Counter", "DT_ActiveEnergy", "DT_kActiveEnergy", "DT_kMeter", "DT_VolumeLiter", "DT_VolumeM3"]
    mq_client = MQSyncReq(zmq.Context())
    msg = MQMessage()

    deviceslist = {}
    msg.set_action('device.get')
    res = mq_client.request('admin', msg.get(), timeout=10)
    if res is not None:
        if 'device.result' in res.get():
            deviceslist = json.loads(res.get()[1])["devices"]

    #print("\n\ndeviceslist = \n%s\n\n" % format(deviceslist))

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
                                
    #print("\n\nsensorslist = \n%s\n\n" % format(sensorslist))
    return sensorslist

# -------------------------------------------------------------------------------------------------
def getMQFilterSensorHistory(id, ts, interval, selector):
        # get the filtered and calculated history starting from/to a certain timestamp
        mq_client = MQSyncReq(zmq.Context())
        msg = MQMessage()
        msg.set_action('sensor_history.get')
        msg.add_data('mode', 'filter')      # Like REST functions sensorHistory_from_filter and sensorHistory_from_to_filter
        msg.add_data('sensor_id', id) 
        msg.add_data('from', ts)        # 
        #msg.add_data('to', 1500847199)     # now
        msg.add_data('interval', interval)    # 'minute|hour|day|week|month|year'
        msg.add_data('selector', selector)     # 'min|max|avg|sum'
        try:
            sensor_history = mq_client.request('admin', msg.get(), timeout=15).get()
        except AttributeError:
            return []
        if 'sensor_history.result' in sensor_history:
            historyvalues = json.loads(sensor_history[1])
            if historyvalues["status"]:
                return historyvalues["values"]["values"]
            else:
                return []
        else:
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
# Common tasks
# -------------------------------------------------------------------------------------------------
package = "plugin_flowmeter"
template_dir = "{0}/{1}/admin/templates".format(get_packages_directory(), package)
static_dir = "{0}/{1}/admin/static".format(get_packages_directory(), package)
logfile = "/var/log/domogik/{0}.log".format(package)

plugin_flowmeter_adm = Blueprint(package, __name__,
                        template_folder = template_dir,
                        static_folder = static_dir)

cli = MQSyncReq(zmq.Context())
msg = MQMessage()
msg.set_action('datatype.get')
res = cli.request('manager', msg.get(), timeout=10)
if res is not None:
    datatypeslist = res.get_data()['datatypes']
else:
    datatypeslist = {}

dttype_color = {'DT_Number': '#BDBDBD', 'DT_Counter': '#BDBDBD', 'DT_ActiveEnergy': '#FE9A2E', 'DT_kActiveEnergy': '#FE9A2E', 'DT_mMeter': '#2E64FE', 'DT_kMeter': '#BDBDBD', 'DT_VolumeLiter': '#1e90ff', 'DT_VolumeM3': '##1e90ff'}


# -------------------------------------------------------------------------------------------------
# Route /
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
# Route /<sensor_id>/<device_name>/graph
# -------------------------------------------------------------------------------------------------
@plugin_flowmeter_adm.route('/<client_id>/<sensor_id>/<device_name>/<data_type>/<interval>/graph')
def graph(client_id, sensor_id, device_name, data_type, interval):
    detail = get_client_detail(client_id)

    data = {}
    data["hour"] = []
    data["day"] = []
    data["month"] = []
    
    if interval == "hour" or interval == "all":
        tsfrom = int((datetime.now() + timedelta(hours=-30)).replace(minute=0, second=0, microsecond=0).strftime("%s"))	# now - 30h
        values = getMQFilterSensorHistory(sensor_id, tsfrom, "hour", "sum")
        if values:
            for timevalue in values:
                valuelist = []
                valuelist.append(int(datetime.strptime(str(timevalue[0]) + "." + str(timevalue[1]) + "." + str(timevalue[3]) + " " + str(timevalue[4]) + ":00:00", "%Y.%m.%d %H:%M:%S").strftime("%s")) * 1000)
                valuelist.append(timevalue[5])
                data["hour"].append(valuelist)            

    if interval == "day" or interval == "all":
        tsfrom = int((datetime.now() + timedelta(days=-32)).replace(minute=0, second=0, microsecond=0).strftime("%s"))	# now - 32j
        values = getMQFilterSensorHistory(sensor_id, tsfrom, "day", "sum")
        if values:
            for timevalue in values:
                valuelist = []
                valuelist.append(int(datetime.strptime(str(timevalue[0]) + "." + str(timevalue[1]) + "." + str(timevalue[3]) + " " + "00:00:00", "%Y.%m.%d %H:%M:%S").strftime("%s")) * 1000)
                valuelist.append(timevalue[4])
                data["day"].append(valuelist)                   

    if interval == "month" or interval == "all":
        tsfrom = int((datetime.now() + timedelta(days=-428)).replace(minute=0, second=0, microsecond=0).strftime("%s"))	# now - 428j
        values = getMQFilterSensorHistory(sensor_id, tsfrom, "month", "sum")
        if values:
            for timevalue in values:
                valuelist = []
                valuelist.append(int(datetime.strptime(str(timevalue[0]) + "." + str(timevalue[1]) + ".01 00:00:00", "%Y.%m.%d %H:%M:%S").strftime("%s")) * 1000)
                valuelist.append(timevalue[2])
                data["month"].append(valuelist)            

    if "unit" in datatypeslist[data_type]:
        dtunit = datatypeslist[data_type]["unit"]
    else:
        dtunit = "-"
        
    try:
        return render_template('plugin_flowmeter_graph.html',
            clientid = client_id,
            client_detail = detail,
            mactive = "clients",
            active = 'advanced',
            devicename = device_name,
            unit = data_type.replace("DT_", "") + " (" + dtunit + ")",
            color = dttype_color[data_type],
            datahour = data["hour"],
            dataday = data["day"],
            datamonth = data["month"],
            interval = interval
            )
    except TemplateNotFound:
        abort(404)


# -------------------------------------------------------------------------------------------------
# Route /log
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


