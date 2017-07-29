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


@author: domos  (domos p vesta at gmail p com)
@copyright: (C) 2007-2016 Domogik project
@license: GPL(v3)
@organization: Domogik
"""

import traceback
import time

class FlowMeterException(Exception):
    """
    Script exception
    """

    def __init__(self, value):
        Exception.__init__(self)
        self.value = value

    def __str__(self):
        return repr(self.value)


class FlowMeter():
    """
    """
    # -------------------------------------------------------------------------------------------------
    def __init__(self, log, send, stop):
        """ Init Weather object
            @param log : log instance
            @param send : callback to send values to domogik
            @param stop : Event of the plugin to handle plugin stop
        """
        self.log = log
        self.send = send
        self.stop = stop
        self.flowMeterSensorsList = {}
        

    # -------------------------------------------------------------------------------------------------
    def updateFlowmeter(self, content):               
        ''' content = {u'timestamp': 1482685199, u'sensor_id': u'199', u'device_id': 87, u'stored_value': u'7.2'}
        '''
        counterSensorId = int(content["sensor_id"])
        counterdiff = int(content["stored_value"]) - int(self.flowMeterSensorsList[counterSensorId]["last_counter_value"])
        self.flowMeterSensorsList[counterSensorId]["last_counter_value"] = content["stored_value"]       # Update last_counter_value
        
        # In case the counter has been reset, what can we do ?
        if counterdiff < 0:
            self.log.warning(u"==> Current counter value of '%s' is less than the last received, Don't save !" % self.flowMeterSensorsList[counterSensorId]["name"])
            return                                  # For now, only ignore the received counter'value, only be save in last_counter_value.
        
        # handle formula if defined
        counterFormula = self.flowMeterSensorsList[counterSensorId]["formula"]
        if counterFormula:
            formula = counterFormula.replace('VALUE', str(float(counterdiff)))
            try:
                flowValue = eval(formula)
            except Exception as exp:
                self.log.error("### Failed to apply formula '{0}' to sensor '{1}': {2}".format(counterFormula, self.flowMeterSensorsList[counterSensorId]["name"], exp))
                return
        else:
            flowValue = counterdiff
        
        self.log.info(u"==> counterdiff = %d, flowValue = %f for flowmeter '%s'" % (counterdiff, flowValue, self.flowMeterSensorsList[counterSensorId]["name"]))

        # If current value and lastcountertimestamp < 30mn don't save (necessary to have one value in hour to calculate sum by interval )
        if flowValue == 0 and (time.time() - self.flowMeterSensorsList[counterSensorId]["last_counter_ts"] < 1800):
            self.log.info(u"==> Current flowmeter value of '%s' = 0 and last timestamp < 30mn, Don't save !" % self.flowMeterSensorsList[counterSensorId]["name"])
            return        
        self.flowMeterSensorsList[counterSensorId]["last_counter_ts"] = content["timestamp"]
        
        #self.log.info(u"==> counterdiff = %d, flowValue = %f for flowmeter '%s'" % (counterdiff, flowValue, self.flowMeterSensorsList[counterSensorId]["name"]))
        if flowValue != "error": self.send(self.flowMeterSensorsList[counterSensorId]["device_id"], counterSensorId, flowValue)
        
    
    # -------------------------------------------------------------------------------------------------
    def doScheduleSum(self):
        self.log.info("==> Do flow sum of ...")
        
        

