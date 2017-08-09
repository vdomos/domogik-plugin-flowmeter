#!/usr/bin/python
# -*- coding: utf-8 -*-

""" This file is part of B{Domogik} project (U{http://www.domogik.org}).

License
=======

B{Domogik} is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

B{Domogik} is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with Domogik. If not, see U{http://www.gnu.org/licenses}.

Plugin purpose
==============

FlowMeter

Implements
==========

- FlowMeterManager

"""

from domogikmq.reqrep.client import MQSyncReq
from domogikmq.message import MQMessage
from domogikmq.reqrep.client import MQSyncReq
from domogik.common.plugin import Plugin

from domogik_packages.plugin_flowmeter.lib.flowmeter import FlowMeter, FlowMeterException
import schedule		# pip install schedule
import threading
import traceback
import json
import time

class FlowMeterManager(Plugin):
    """ 
    """

    # -------------------------------------------------------------------------------------------------
    def __init__(self):
        """ Init plugin
        """
        Plugin.__init__(self, name='flowmeter')

        # check if the plugin is configured. If not, this will stop the plugin and log an error
        if not self.check_configured():
            return

        # get the devices list
        self.devices = self.get_device_list(quit_if_no_device = True)

        # get the sensors id per device : 
        self.sensors = self.get_sensors(self.devices)

        # Init FlowMeter Manager
        self.flowmetermanager = FlowMeter(self.log, self.send_data, self.getMQFilterSensorHistory, self.get_stop())
        
        # Set nodes list
        self.setFlowMeterSensorsList(self.devices)

        schedule.every(5).minutes.do(self.flowmetermanager.doScheduleSum)        
        
        # A thread is launched to run schedule loop.
        self.log.info(u"==> Launch 'schedule loop' thread") 
        thr_name = "thr_schedule"
        self.thread_schedule = threading.Thread(None,
                                          self.scheduleLoop,
                                          thr_name,
                                          (),
                                          {})
        self.thread_schedule.start()
        self.register_thread(self.thread_schedule)
        
        self.log.info(u"==> Subscribe to MQ 'device-stats' messages") 
        self.add_mq_sub("device-stats")

        self.log.info(u"==> Add callback for new or changed devices.")
        self.register_cb_update_devices(self.reload_devices)           # "reload_devices" never call, don't work when using on_message() function !
        
        self.ready()


    # -------------------------------------------------------------------------------------------------
    def setFlowMeterSensorsList(self, devices):
        self.log.info(u"==> Set FlowMeter sensors list ...")
  
        for a_device in devices:    # For each device
            # self.log.info(u"==> a_device:   %s" % format(a_device))
            device_id = a_device["id"]                                          # 
            device_name = a_device["name"]                                      # 
            flowsensor_id = a_device["sensors"]["flow"]["id"]
            #sensorid = a_device["sensors"]["diffcounter"]["id"]
            counterid = self.get_parameter(a_device, "counter")                 # Device Parameter
            formula = self.get_parameter(a_device, "formula")                   # Device Parameter
            unit = self.get_parameter(a_device, "unit")                         # Device Parameter
            periodic = True if self.get_parameter(a_device, "periodic") == "y" else False       # Device Parameter

            last_countervalue = self.getMQValue(counterid)
            if last_countervalue == "Failed":
                self.log.error(u"Reading last device's counter value for '%s' failed, Counter ignored.", device_name)
            else:
                self.flowmetermanager.flowMeterSensorsList.update({counterid : {"name": device_name, 
                                                                                "device_id": device_id, 
                                                                                "flowsensor_id": flowsensor_id,
                                                                                "formula": formula,
                                                                                "unit": unit,            # Utile pour generer graphes dans 'Advanced' ?
                                                                                "periodic": periodic,
                                                                                "last_counter_value": last_countervalue,
                                                                                "last_counter_ts": 0}})       
                self.log.info(u"==> Device Flowmeter Sensor for counter '%d' : '%s'" % (counterid, format(self.flowmetermanager.flowMeterSensorsList[counterid])))
                #self.log.info(u"==> Device Flowmeter Sensor list : %s" % self.flowmetermanager.flowMeterSensorsList)
                # {85: {'name': u'Vitesse du vent', 'counter': 210, 'dmgid': 85, 'formula': u'VALUE * 10', 'unit': u'km/h', 'lastcountervalue': u'10239534'}, 
                #  86: {'name': u'Consommation eau', 'counter': 208, 'dmgid': 86, 'formula': u'VALUE * 4', 'unit': u'l', 'lastcountervalue': u'148920'}}
                
                if not self.flowmetermanager.flowMeterSensorsList[counterid]["periodic"]:
                    self.log.info(u"==> Device Flowmeter Sensor for counter '%s' does not have a periodic update, Not supported for now !" % self.flowmetermanager.flowMeterSensorsList[counterid]["name"])

    # -------------------------------------------------------------------------------------------------
    def getMQValue(self, id):
        """  REQ/REP message to get sensor value
        """
        mq_client = MQSyncReq(self.zmq)
        msg = MQMessage()
        msg.set_action('sensor_history.get')
        msg.add_data('sensor_id', id)
        msg.add_data('mode', 'last')
        try:
            sensor_history = mq_client.request('admin', msg.get(), timeout=10).get()  
            #self.log.info(u"==> 0MQ REQ/REP: Last sensor history: %s" % format(sensor_history))  
            # sensor_history is a list   ['sensor_history.result', '{"status": true, "reason": "", "sensor_id": 183, "values": [{"timestamp": 1452017810.0, "value_str": "7.0", "value_num": 7.0}], "mode": "last"}']
            sensor_last = json.loads(sensor_history[1])
            if sensor_last['status'] == True:
                sensor_timestamp = sensor_last['values'][0]['timestamp']  
                sensor_value = sensor_last['values'][0]['value_str']
                self.log.info(u"==> 0MQ REQ/REP: Last sensor '%d' value: %s (%s)" % (id, sensor_value , time.strftime("%d/%m/%Y %H:%M:%S", time.localtime(sensor_timestamp))))
                return sensor_value
            else:
                self.log.info(u"==> 0MQ REQ/REP: Last sensor '%d' status = FALSE" % id)
                return "Failed"
        except AttributeError:  # For some error like: 'NoneType' object has no attribute 'get'
            self.log.error(u"### 0MQ REQ/REP: '%s'", format(traceback.format_exc()))
            return "Failed"
        

    # -------------------------------------------------------------------------------------------------
    def getMQFilterSensorHistory(self, id, ts, interval, selector):
        # get the filtered and calculated history starting from/to a certain timestamp
        #cli = MQSyncReq(zmq.Context())
        mq_client = MQSyncReq(self.zmq)
        msg = MQMessage()
        msg.set_action('sensor_history.get')
        msg.add_data('mode', 'filter')          # Like REST functions sensorHistory_from_filter and sensorHistory_from_to_filter
        msg.add_data('sensor_id', id) 
        msg.add_data('from', ts)                # 
        #msg.add_data('to', 1500847199)         # Default now
        msg.add_data('interval', interval)      # 'minute|hour|day|week|month|year'
        msg.add_data('selector', selector)      # 'min|max|avg|sum'
        try:
            #sensor_history = cli.request('admin', msg.get(), timeout=15).get()
            sensor_history = mq_client.request('admin', msg.get(), timeout=15).get()
        except AttributeError:
            self.log.error("### AttributeError for get FilterSensorHistory")
            return []
        if 'sensor_history.result' in sensor_history:
            historyvalues = json.loads(sensor_history[1])
            if historyvalues["status"]:
                return historyvalues["values"]["values"]
            else:
                self.log.error("### Status : False, Reason : '%s'" % historyvalues["reason"])
                return []
        else:
            self.log.error("### No Result for FilterSensorHistory: '%s'" % format(sensor_history))
            return []
 
    # -------------------------------------------------------------------------------------------------
    def on_message(self, msgid, content):               
        ''' Must recieve only 'device-stats' messages
            but received 'device.update' too ! => ticket done
        '''
        #self.log.debug(u"==> Receive MQ '%s' content: %s" % (msgid, format(content)))
        if msgid == 'device-stats':
            # ==> Receive MQ 'device-stats' content: {u'timestamp': 1500937509, u'sensor_id': u'210', u'device_id': 32, u'stored_value': u'10240971'}
            if int(content["sensor_id"]) not in self.flowmetermanager.flowMeterSensorsList: return
            self.flowmetermanager.updateFlowmeter(content)


    # -------------------------------------------------------------------------------------------------
    def send_data(self, countersensorid, sensortype, value):
        """ Send the flowmeter sensors values over MQ
        """
        data = {}
        device_id = self.flowmetermanager.flowMeterSensorsList[countersensorid]["device_id"]
        devicename = self.flowmetermanager.flowMeterSensorsList[countersensorid]["name"]
        data[self.sensors[device_id][sensortype]] = value                 
        self.log.info("==> Publish '%s' value '%s' for device '%s'" % (sensortype, value, devicename))

        try:
            self._pub.send_event('client.sensor', data)
        except:
            self.log.error(u"### Bad MQ message to update sensor : {0}".format(data))
            pass

    
    # -------------------------------------------------------------------------------------------------
    def scheduleLoop(self):
        """
        """
        while not self.get_stop().isSet():
            schedule.run_pending()
            self.get_stop().wait(1)                   # Sleep


    # -------------------------------------------------------------------------------------------------
    def reload_devices(self, devices):
        """ Called when some devices are added/deleted/updated, 
            Don't be called when using on_message() function !
        """
        self.log.info(u"==> Reload Device called")
        self.flowmetermanager.flowMeterSensorsList(devices)
        self.devices = devices
        self.sensors = self.get_sensors(devices)


if __name__ == "__main__":
    flowmeter = FlowMeterManager()
